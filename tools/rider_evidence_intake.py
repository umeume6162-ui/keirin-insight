"""Build rider publication candidates from explicitly supplied evidence.
No network calls, no invented approvals, no production writes.
"""
import argparse
import datetime
import json
import pathlib
import re
from urllib.parse import urlsplit, parse_qs
from prepare_verified_release import need, official, day, norm, digest, review

FIELDS=("name","prefecture","period","id")

def candidate(observation, approval):
    need(isinstance(observation,dict) and isinstance(approval,dict),"invalid evidence record")
    facts=observation.get("observedFacts")
    need(isinstance(facts,dict) and all(isinstance(facts.get(f),str) and norm(facts[f]) for f in FIELDS),"four directly observed values required")
    rid=facts["id"]
    source=observation.get("source")
    need(re.fullmatch(r"[0-9]{6}",rid) and re.fullmatch(r"[0-9]+",facts["period"]),"invalid identity format")
    need(official(source) and urlsplit(source).path=="/pc/racerprofile" and parse_qs(urlsplit(source).query).get("snum")==[rid],"official profile identity mismatch")
    need(observation.get("method")=="direct_official_profile","direct official profile observation required")
    stamp=observation.get("retrievedAt")
    need(isinstance(stamp,str),"retrieval time required")
    t=datetime.datetime.fromisoformat(stamp.replace("Z","+00:00"))
    need(t.tzinfo is not None,"timezone required")
    jst=datetime.timezone(datetime.timedelta(hours=9))
    verified=t.astimezone(jst).date().isoformat()
    observer=observation.get("observer")
    reviewer=approval.get("reviewer")
    need(isinstance(observer,str) and observer.strip() and isinstance(reviewer,str) and reviewer.strip() and observer.strip()!=reviewer.strip(),"separate named observer and reviewer required")
    need(approval.get("status")=="approved" and approval.get("observationSha256")==digest(observation),"independent approval absent or observation changed")
    need(day(approval.get("reviewedDate")) and verified<=approval["reviewedDate"],"approval date invalid")
    need(isinstance(observation.get("evidenceNote"),str) and observation["evidenceNote"].strip(),"source evidence note required")
    record={f:facts[f] for f in FIELDS}
    record.update(source=source,verifiedDate=verified,officialVerification={"status":"verified","fields":list(FIELDS),"source":source,"method":"direct_official_profile"})
    # The approval must bind the exact candidate record as well as its observation.
    need(approval.get("recordSha256")==digest(record),"approved candidate hash mismatch")
    e={"kind":"rider","key":rid,"status":"approved","recordSha256":digest(record),"source":source,"reviewedDate":approval["reviewedDate"],"reviewer":reviewer,"observedFacts":facts,"retrievedAt":stamp,"evidenceNote":observation["evidenceNote"],"observationSha256":digest(observation),"observer":observer}
    review(record,"rider",rid,{("rider",rid):e})
    return record,e

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--observation",type=pathlib.Path,required=True)
    p.add_argument("--approval",type=pathlib.Path,required=True)
    p.add_argument("--output",type=pathlib.Path,required=True)
    a=p.parse_args()
    obs=json.loads(a.observation.read_text(encoding="utf-8"))
    app=json.loads(a.approval.read_text(encoding="utf-8"))
    record,evidence=candidate(obs,app)
    with a.output.open("x",encoding="utf-8") as f:
        json.dump({"schema":"ki-rider-evidence-candidate-v1","publicationStatus":"candidate_only","record":record,"review":evidence,"observation":obs,"approval":app},f,ensure_ascii=False,indent=2)
    print("Candidate saved; publication not performed.")

if __name__=="__main__":
    main()

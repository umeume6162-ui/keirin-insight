"""Conservative audit of evidence intake records; never grants approval."""
def audit(records):
    results=[]
    for record in records:
        missing=[k for k in ("recordId","url","observedAt","method","originalEvidenceRef") if not isinstance(record.get(k),str) or not record[k].strip()]
        results.append({"recordId":record.get("recordId"),"missing":missing,"status":"REVALIDATION_REQUIRED" if missing else "ORIGINAL_REVIEW_REQUIRED","publicationAllowed":False,"trainingAllowed":False})
    return results

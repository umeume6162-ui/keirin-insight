# KEIRIN INSIGHT — 公式結果原本ルートの実証・安全な照合手順

確認日: 2026-11-23 JST（調査対象は2026-11-20の前橋/名古屋等の研究候補）
**現状: 検証用プログラム作成済み、公式原本の個別レース直接取得は未成功、正式公開0件。**

## 決定的な技術的手掛かり（第三者の調査資料、公式API文書ではない）
2026年10月2日付の公開技術調査:
https://github.com/keirin-platform/keirin-platform/blob/main/docs/keirin-jp-api.md

この資料によると、KEIRIN.JPのブラウザ画面は内部の JSON API を使用:
- `JSJ057`：日別開催情報・開催トークン
- `JSJ001`：開催ヘッダ・レーストークン
- `JSJ002` / `JSJ006`：出走表・選手登録番号
- `JSJ012`：個別レース確定結果（`tyakujyunItemSubData`、着順・車番・着差・上がり・決まり手・B/H、個人状況）
- `JSJ018`：開催結果一覧（1〜3着など、7/9車の詳細原本とは別）

**注意**：これは他の開発者の検証記録であり、JKAが外部再利用を許可した公式API仕様ではない。結果APIをこのプロジェクトが実際に叩き、取得できたことの証明ではない。

KEIRIN.JPの `https://keirin.jp/robots.txt`（2026-11-23確認）には `Disallow:/` と一部公開ページだけの `Allow:` があり、`/pc/json` は許可例外にない。このため、**同JSONの自動取得・大量巡回・公開再配信は本作業では実行しない**。利用規約・再利用許諾・正規の取得方法を別途確認する。技術的に可能という情報と、利用許諾があるという情報は同じではない。

## 公式原本を適法に得られた場合の最短照合

1. 許諾されたKEIRIN.JPの結果画面、主催者の正式結果資料、あるいは利用条件上正規に入手した原本を、日付・場コード・Rが分かる形で確認する。
2. 元の出走表や変更後出走表で7/9車全員を確認。欠車・取消は「出走していない選手」、落・失などは「結果表に例外状態を持つ選手」と区別する。
3. 原資料を**公開GitHubに丸ごとアップロードせず**、引用・利用可能な最小限の照合項目の構造化証拠を権限を確認して保管する。
4. `tools/audit_official_primary_candidate.cjs` はユーザーが確認した公式原本の構造化データと研究候補を読み取り専用で比較し、氏名、車番、数字/例外着順、上がり、着差、決まり手、S/B、元の例外表記を検査する。**公式原本データ自体は現在まだ提供・取得されていない。**
5. 公式原本との一致に加えて別媒体の独立掲載内容で必須項目を照合し、最終的な正式フィードの検査を通す。照合ツールの返値は `publicationPassed:false` 固定で、公式PASSへの自動移送はしない。
6. 公式原本の証拠が不明・欠損・取得失敗なら保留を維持し、足りない項目だけ追加照合する。2媒体で同じ空欄でも数値やSマークは創作しない。

### 監査用入力データの考え方
出典を確認したときだけ `schema=ki-official-primary-transcription-v1`、`raceKey`、`issuer=JKA_KEIRIN_JP` または `ORGANIZER`、`sourceUrl`、`retrievedDateJST`、`retrievalMethod`、`originalRecordVerified`、`results[]` を組み立てる。`results[]` の各行は `car,name,finishRaw,lapSeconds,marginRaw,winningMethodRaw,sbRaw,exceptionRaw` を保持する。

**絶対禁止**：Kドリームスなど研究候補の内容をそのままコピーして、架空の公式 `issuer` と `sourceUrl` を付けること。テスト用の一致データも公式原本取得の証拠ではない。個人の自己申告フラグ `originalRecordVerified:true` のみで原本の真正性を保証できないため、最終承認には実際の出典・取得記録の独立確認が必要。

## 関連ファイル
- `tools/audit_official_primary_candidate.cjs`：読み取り専用フィールド照合
- `tools/test_audit_official_primary_candidate.cjs`：欠損、偽の公式証拠、相違、媒体欄欠損の回帰テスト
- `tools/source-origin-audits/2026-11-20_22_2.origin-review.json`：公式未取得と媒体ごとに実証済みの項目を明記した監査
- `tools/reconstruction-candidates/*`：正式公開と分離した既存研究候補
- `.github/workflows/check-publication-feeds.yml`：静的データ完全性テスト（実行成功は別途要確認）

# 選手ID公式照合証拠台帳 v15.8
このテンプレートは空の入力形式であり、実データや承認を含まない。
運用台帳はアクセス制御された保存先に置き、公開リポジトリに証拠原本や担当者情報を置かない。
## 入力
entries の各要素は status と observation を持つ。status は pending / rejected / approved のいずれか。
observation は公式ページを直接観測できた場合だけ作成し、observedFacts (name, prefecture, period, id の文字列)、source (公式プロフィールURL)、method (direct_official_profile)、retrievedAt (タイムゾーン付きISO日時)、observer、evidenceNote を記録する。アクセス不能時は証拠を作らず既存の未照合台帳に残す。evidenceNote には取得根拠と保存した原本の参照を記載する。
approved にする場合のみ独立した審査者が approval を添付する。approval は status=approved, reviewer, reviewedDate, observationSha256, recordSha256 を含む。ハッシュは prepare_verified_release.digest の正規化方式に一致する必要がある。別名の入力だけで独立性が保証されるわけではない。審査者は元の公式資料を確認する。
## 実行
```sh
python tools/rider_evidence_batch.py --ledger /private/ledger.json --output /private/candidates.json
```
出力は候補のみ。正式配信ファイルは変更しない。既存出力の上書きは拒否する。
公開前は全4配信ファイル、独立承認台帳、訂正記録を prepare_verified_release.py に渡し、最終検査と別途公開承認を行う。
## 現状
実際の外部台帳との接続、審査者の認証、公式原本の保存、実行検証は未完了。テンプレートを承認済み実績として数えない。

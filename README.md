# KEIRIN INSIGHT

**運用仕様の正本は [V4運用仕様](tools/STAGED_INTAKE_V4.md) だけです。** 新しいチャットへ移行したら、まずこのファイルの「チャット移行時の最短復旧手順（最重要）」を読むこと。過去のチャット全文や進捗報告は最新の指示ではありません。

## 現在の最優先開発

**GitHub Actions/Pythonで日々の全開催・全級班（7/9車）の出走表と結果を取得 → Googleスプレッドシートへ重複なく保存 → GitHub Pagesで日付別に表示。** 初期はA級7車ミッドナイト優先、iPhone中心で運用。収集済みでも独立照合前のデータは正式PASSと区別。

- **このチャットの担当**：日次開催・出走表・結果の収集元確保、GitHubからGoogleへのupsert、日次JSONの更新、サイト表示、稼働監視、GASからの段階的移行。
- **既存自動タスクの担当**：選手IDと過去レース/発走前ラインの照合、既存2集計JSONの同期。手動の過去照合へ戻さない。
- **日次保存先（2026-11-23）**：`KI｜日次出走表` sheetId `2101100610`へ西武園1R・A3の全7車をGoogle接続経由で保存・再読済み（未正式照合）。`KI｜日次結果` sheetId `2101100611`はヘッダのみ。
- **実装済み・検証済みの区別**：`scripts/collect_tospo_entry.py`で東スポ公開HTMLから西武園1Rの実7車をGitHub上で抽出成功。Google取り込み形式検証・dry-runは成功。`scripts/upsert_daily_sheets.py --apply`は**GitHub認証資格情報でHTTP 403 Forbidden**のため失敗。Google接続ツール経由の7行保存は成功し、`daily-board-feed-v1.json`にも反映済み（GitHub commit `8299b508...`）。`daily-board.html`実サイト表示、全開催自動取得、結果収集、GitHubからGoogleへの直接書込は未完成・未確認。PR #2はオフライン自己検査のみでmainに統合済み（`ed2cfadf...`）。
- **次の着手点**：①Google共有権限でGitHub用とみられるサービスアカウントが`reader`と判明。Secret側の同一性確認と明示承認後の`writer`付与によって403を解消（閲覧は成功、保存だけ拒否）②固定URLから日次開催・R発見へ収集器を拡張 ③GitHubから1Rの実upsert成功/再実行の重複0確認 ④結果取得・例外照合 ⑤定期更新とサイト公開表示の実確認。GASは新経路の安定後にだけ停止。
- **重要な別系統障害**：2026-11-23のGitHub Actionsログで従来の`scripts/build_feeds.py`にSyntaxError（line 208）。最新mainでの修復・再実行成功は未確認。影響を切り分けて対処。

## 品質・引き継ぎ

正式verified-*データの公開は既存V4の2媒体照合・全車検査に従う。通常CIは公開データ整合と画面静的契約の2検査、深掘りは必要時手動。データ/証拠を守り、重複した旧コード・GASトリガーは代替経路の動作確認後だけ停止/削除する。Googleのシート設計・作成・安全な整理はユーザーが実務判断を委任済み。既存の正式仕様を別ファイルへ複製しない。

**「作業の続き」では、V4の移行手順を確認して未実装の最優先工程へ着手し、接続できるGitHub/Googleを直接操作する。** 同じ説明をユーザーに求めない。

## リンク

- [現行V4運用仕様](tools/STAGED_INTAKE_V4.md)
- [本番Googleスプレッドシート](https://docs.google.com/spreadsheets/d/1gCe5q5STYH0T8XKqxJbVawB0Cl8TPsCISFJiRUdA02M/edit)
- [KEIRIN INSIGHT](https://umeume6162-ui.github.io/keirin-insight/)
- [日次出走表・結果ページ](https://umeume6162-ui.github.io/keirin-insight/daily-board.html)

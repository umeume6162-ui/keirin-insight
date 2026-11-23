# KEIRIN INSIGHT

**運用仕様の正本は [V4運用仕様](tools/STAGED_INTAKE_V4.md) だけです。** 新しいチャットへ移行したら、まずこのファイルの「チャット移行時の最短復旧手順（最重要）」を読むこと。過去のチャット全文や進捗報告は最新の指示ではありません。

## 現在の最優先開発

**GitHub Actions/Pythonで日々の全開催・全級班（7/9車）の出走表と結果を取得 → Googleスプレッドシートへ重複なく保存 → GitHub Pagesで日付別に表示。** 初期はA級7車ミッドナイト優先、iPhone中心で運用。収集済みでも独立照合前のデータは正式PASSと区別。

- **このチャットの担当**：日次開催・出走表・結果の収集元確保、GitHubからGoogleへのupsert、日次JSONの更新、サイト表示、稼働監視、GASからの段階的移行。
- **既存自動タスクの担当**：選手IDと過去レース/発走前ラインの照合、既存2集計JSONの同期。手動の過去照合へ戻さない。
- **Googleに作成済み（日次保存先・まだヘッダのみ）**：`KI｜日次出走表`（sheetId `2101100610`）、`KI｜日次結果`（sheetId `2101100611`）。
- **実装済み**：`daily-board.html`、`daily-board-feed-v1.json`、`scripts/build_daily_board.py`、`.github/workflows/update-daily-board.yml`。現在のJSON生成は旧Sheetsを**読取専用**で使用。新2タブへの収集/書込と新タブからの配信は未完成。ワークフローの存在は実行成功・最新データ取得を意味しない。
- **次の着手点**：日次データソース確認 → GitHubから新2タブへの書込権限・upsert検証 → 1開催の収集から画面反映まで実証 → 全開催へ拡張。GAS本体とトリガーの依存関係が確認できるまで旧処理を停止しない。
- **重要な別系統障害**：2026-11-23のGitHub Actionsログで従来の`scripts/build_feeds.py`にSyntaxError（line 208）。最新mainでの修復・再実行成功は未確認。影響を切り分けて対処。

## 品質・引き継ぎ

正式verified-*データの公開は既存V4の2媒体照合・全車検査に従う。通常CIは公開データ整合と画面静的契約の2検査、深掘りは必要時手動。データ/証拠を守り、重複した旧コード・GASトリガーは代替経路の動作確認後だけ停止/削除する。Googleのシート設計・作成・安全な整理はユーザーが実務判断を委任済み。既存の正式仕様を別ファイルへ複製しない。

**「作業の続き」では、V4の移行手順を確認して未実装の最優先工程へ着手し、接続できるGitHub/Googleを直接操作する。** 同じ説明をユーザーに求めない。

## リンク

- [現行V4運用仕様](tools/STAGED_INTAKE_V4.md)
- [本番Googleスプレッドシート](https://docs.google.com/spreadsheets/d/1gCe5q5STYH0T8XKqxJbVawB0Cl8TPsCISFJiRUdA02M/edit)
- [KEIRIN INSIGHT](https://umeume6162-ui.github.io/keirin-insight/)
- [日次出走表・結果ページ](https://umeume6162-ui.github.io/keirin-insight/daily-board.html)

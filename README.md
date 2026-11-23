# KEIRIN INSIGHT

**運用仕様の正本は [V4運用仕様](tools/STAGED_INTAKE_V4.md) だけです。** 新しいチャットへ移行したら、まずこのファイルの「チャット移行時の最短復旧手順（最重要）」を読むこと。過去のチャット全文や進捗報告は最新の指示ではありません。

## 現在の最優先開発

**GitHub Actions/Pythonで日々の全開催・全級班（7/9車）の出走表と結果を取得 → Googleスプレッドシートへ重複なく保存 → GitHub Pagesで日付別に表示。** 初期はA級7車ミッドナイト優先、iPhone中心で運用。収集済みでも独立照合前のデータは正式PASSと区別。

- **このチャットの担当**：日次開催・出走表・結果の収集元確保、GitHubからGoogleへのupsert、日次JSONの更新、サイト表示、稼働監視、GASからの段階的移行。
- **既存自動タスクの担当**：選手IDと過去レース/発走前ラインの照合、既存2集計JSONの同期。手動の過去照合へ戻さない。
- **日次保存先（2026-11-23実測）**：Google `KI｜日次出走表`（sheetId `2101100610`）で**33レース・231車**、`KI｜日次結果`（sheetId `2101100611`）は**西武園2026-11-23 1Rの7車を初収録**。日次は取得済み・未正式照合であり、既存V99・正式PASSとは分離する。
- **実データ保存実績**：PR #9 Run #78でサービスアカウントのA1同値書込成功、PR #10 Run #83で静岡1Rの新規7車保存・再実行重複0を実証。**PR #11 Run #98では静岡・松山・奈良の32R/224車を検査し、GitHubからGoogleへ新規217行・既存一致7行・変更0行、再実行追加0行を実証。** 奈良の3R等、7/9車を満たさない表は拒否。
- **新たな定期自動化**：43場コードの対応表を持つ`scripts/discover_tospo_races.py --all-venues`でレース一覧の掲載場・日付・全車を確認。既存`.github/workflows/update-daily-board.yml`の定期scheduleに`scripts/auto_daily_tospo_intake.py --apply --days 2 --max-venues 43`を追加し、JSTの当日・翌日を有限探索→変更0件の候補のみGoogleへ差分保存→日次配信JSON生成の順に実行。**PR #14 Run #115で4場48Rの模擬検査成功、1場12R/108車の単位で分割保存する構造へ更新済み（旧全日36R制限撤廃）。新しいschedule経路の実動作は未確認**。全開催完全収集・日次結果・Safari実機表示は引き続き未完成。
- **日次結果取得・保存（2026-11-23実証）**：PR #15 Run #126で西武園1Rのnetkeirin＋チャリロト実結果7車が不一致0、出走表との選手照合も合格し、GitHubからGoogle `KI｜日次結果`へ新規7行保存、2回目追加0、対象行再読成功。**正式PASSではない**。既存日次GitHub scheduleに`auto_daily_results.py --apply --max-races 4`を追加し、翌日以降も全車・2媒体・事前照合に通ったRだけ個別保存。実schedule成功と全R網羅は未確認。
- **iPhone時間帯別表示**：日次ページにモーニング・デイ・ナイター・ミッドナイトと時間帯未確認のフィルターを追加。裏付けのある時間帯メタデータが来るまでは未知と表示し、R番号から推定しない。
- **次の着手点**：①定期実行ログとGoogle追加行の再読を確認 ②未取得開催場・Rの上流取得方法を拡張 ③日次結果7/9車と例外の収集・保存 ④日次サイト公開画面の実確認。GASを停止するのは新経路の安定後だけ。
- **過去結果の実HTML取得・2媒体比較（2026-11-23）**：GitHub Actions PR #3 Run #47で京王閣2026-09-10 2Rの全7車をnetkeirinとチャリロトから実取得し、共通比較器で**不一致0件**。`formalPass:false`で上流独立性確認待ち。LotoPlaceはrobots確認不能のため自動取得しない。PR #3は一時検証コードを除去し、通常の読み取り専用手動プレビュー経路だけmainへ統合。**手動dispatch経路の実行成功・Google保存・正式PASSは未実証**。
- **重要な別系統障害**：2026-11-23のGitHub Actionsログで従来の`scripts/build_feeds.py`にSyntaxError（line 208）。最新mainでの修復・再実行成功は未確認。影響を切り分けて対処。

## 品質・引き継ぎ

正式verified-*データの公開は既存V4の2媒体照合・全車検査に従う。通常CIは公開データ整合と画面静的契約の2検査、深掘りは必要時手動。データ/証拠を守り、重複した旧コード・GASトリガーは代替経路の動作確認後だけ停止/削除する。Googleのシート設計・作成・安全な整理はユーザーが実務判断を委任済み。既存の正式仕様を別ファイルへ複製しない。

**「作業の続き」では、V4の移行手順を確認して未実装の最優先工程へ着手し、接続できるGitHub/Googleを直接操作する。** 同じ説明をユーザーに求めない。

## リンク

- [現行V4運用仕様](tools/STAGED_INTAKE_V4.md)
- [本番Googleスプレッドシート](https://docs.google.com/spreadsheets/d/1gCe5q5STYH0T8XKqxJbVawB0Cl8TPsCISFJiRUdA02M/edit)
- [KEIRIN INSIGHT](https://umeume6162-ui.github.io/keirin-insight/)
- [日次出走表・結果ページ](https://umeume6162-ui.github.io/keirin-insight/daily-board.html)

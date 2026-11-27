# KEIRIN INSIGHT

運用仕様の正本は [V4運用仕様](tools/STAGED_INTAKE_V4.md) です。作業を引き継ぐときは、V4の「チャット移行・次回作業の最短手順」から確認してください。

## 運用

- **日次収集**は [日次Actions](.github/workflows/update-daily-board.yml) が担当します。出走表と結果を既存のGoogle台帳に保存し、日次配信と日付別履歴を更新します。
- **照合・正式登録**は結果・事前ライン担当と選手ID担当が行います。合格条件と書込先は [V4 §2〜6](tools/STAGED_INTAKE_V4.md) を確認してください。
- **サイト監視・集計**は既存Actionsが担当します。GASや旧台帳の利用状況と保護条件もV4に記載しています。
- 過去の実測値、試験、旧仕様はGitの変更履歴を参照してください。

## 競輪・競馬共通の予想仕様

サイト内で開催・レースを選び、発走前のデータから予想と根拠を表示し、確定後の結果検証に接続する方針は [V4 §1](tools/STAGED_INTAKE_V4.md#1-目的正本と優先順位) を参照してください。

## リンク

- [KEIRIN INSIGHT｜予想・研究](https://umeume6162-ui.github.io/keirin-insight/)
- [正式な並び予想と確定結果](https://umeume6162-ui.github.io/keirin-insight/line-forecast.html)
- [日次出走表・結果](https://umeume6162-ui.github.io/keirin-insight/daily-board.html)
- [本番Googleスプレッドシート](https://docs.google.com/spreadsheets/d/1gCe5q5STYH0T8XKqxJbVawB0Cl8TPsCISFJiRUdA02M/edit)

# KEIRIN INSIGHT

**正式な現行仕様は [V4運用仕様](tools/STAGED_INTAKE_V4.md) の1ファイルだけです。** 過去の進捗報告や版ごとの古い仕様を運用ルールとして再利用しません。GitHubの変更履歴に旧版は残ります。Googleシート `KI｜引き継ぎ・共通仕様` は要点とリンクだけの控えです。

## 作業開始時に行うこと

1. [V4運用仕様](tools/STAGED_INTAKE_V4.md) と最新の本番台帳・公開フィードを確認。過去報告の固定件数を最新数としない。
2. 既存の手動・自動受付と公開フィードを重複照合し、未合格の選手/レースを複数件まとめて処理する。新規資料取得も並行する。
3. 4必須選手同定項目、全7/9車結果、別建ての発走前ラインに必要な2掲載サイト一致を確認して必要な証拠を保存し、変更行だけ再読する。
4. 合格した対象を既存の公開経路へ連携。**保存・PASS・正式フィード・CI成功・実サイト表示は区別**する。失敗を2回繰り返すレースは別レースに切替える。

## 検査の役割

- **通常pushの2つだけ**：`tools/check_publication_completeness.cjs`（正式フィード整合）と`tools/test_mobile_result_contract.cjs`（UI静的表示契約）。重複する全レース照合を両方で実行しない。
- **詳細7検査**：PR/手動、関連する再構築・例外・スキーマ変更時に使用。通常の1人・1R追加ごとに過去全件検査を行わない。
- GASの本体/トリガー参照は未確認。旧Googleシートの履歴やデータは削除しない。既存`KI｜タブ棚卸`に重複状況を記録。

## リンク

- [本番Googleスプレッドシート](https://docs.google.com/spreadsheets/d/1gCe5q5STYH0T8XKqxJbVawB0Cl8TPsCISFJiRUdA02M/edit)
- [公開サイト](https://umeume6162-ui.github.io/keirin-insight/)
- [現行V4運用仕様](tools/STAGED_INTAKE_V4.md)

**引き継ぎ・チャット移行の際はこのREADMEと現行V4だけを参照し、旧仕様を重ねて読み込まない。**

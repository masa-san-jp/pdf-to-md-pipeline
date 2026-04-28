/**
 * Gemini API との通信を担当するサービス。
 * ドキュメントをMarkdown形式で抽出し、ファイル名を提案する。
 */
var GeminiService = (function () {

  var PROMPT = [
    '以下のドキュメントを分析してください。',
    '',
    '## タスク1: テキスト抽出・Markdown再構築',
    'ドキュメントの全内容を忠実にMarkdown形式で再構築してください。',
    '- 見出し・セクション構造は # ## ### で表現する',
    '- 表は Markdown テーブル（| col | col |）で表現する',
    '- 箇条書きは - または 1. で表現する',
    '- 太字・強調は **テキスト** で表現する',
    '- 手書き文字も可能な限り正確に読み取る',
    '- ページ番号・ヘッダー・フッターの繰り返し要素は除外してよい',
    '- テキストが存在しない画像・図は「[図: 説明]」と記述する',
    '',
    '## タスク2: ファイル名の提案',
    'このドキュメントの内容を表す簡潔なファイル名（日付プレフィックスを除く）を提案してください。',
    'ルール:',
    '- 文書の種別と主要な固有名詞・日付を含める',
    '- 例: 請求書_ABC株式会社_2026年4月分, 契約書_業務委託_XYZ社, 議事録_経営会議_20260428',
    '- 日本語可、スペース不可、区切りはアンダースコア',
    '- OS禁則文字（/ \\ : * ? " < > |）は使用しない',
    '- 最大50文字',
    '',
    '## 出力形式',
    '以下のJSONのみを返してください（前後に余分なテキスト・コードブロック記号は不要）:',
    '{',
    '  "filename": "文書種別_キーワード",',
    '  "content": "# Markdownの全文..."',
    '}',
  ].join('\n');

  /**
   * ドキュメントをGeminiで解析し、Markdownとファイル名を返す。
   * @param {string} base64Data - Base64エンコードされたファイルデータ
   * @param {string} mimeType - ファイルのMIMEタイプ
   * @returns {{ filename: string, content: string }|null}
   */
  function extract(base64Data, mimeType) {
    var apiUrl = 'https://generativelanguage.googleapis.com/v1beta/models/'
      + CONFIG.GEMINI_MODEL + ':generateContent?key=' + CONFIG.GEMINI_API_KEY;

    var payload = {
      contents: [{
        parts: [
          { text: PROMPT },
          { inline_data: { mime_type: mimeType, data: base64Data } },
        ],
      }],
      generationConfig: {
        response_mime_type: 'application/json',
      },
    };

    var options = {
      method: 'post',
      contentType: 'application/json',
      payload: JSON.stringify(payload),
      muteHttpExceptions: true,
    };

    try {
      var response = UrlFetchApp.fetch(apiUrl, options);
      var status = response.getResponseCode();

      if (status !== 200) {
        Logger.log('Gemini API error: ' + status);
        return null;
      }

      var json = JSON.parse(response.getContentText());
      var text = json.candidates[0].content.parts[0].text;

      // モデルがコードブロックで囲んだ場合のフォールバック
      text = text.replace(/^```json\s*/i, '').replace(/```\s*$/, '').trim();

      var result = JSON.parse(text);

      if (typeof result.filename !== 'string' || typeof result.content !== 'string') {
        Logger.log('Gemini response missing required fields');
        return null;
      }

      return {
        filename: result.filename,
        content: result.content,
      };
    } catch (e) {
      Logger.log('GeminiService.extract error: ' + e.toString());
      return null;
    }
  }

  return { extract: extract };
})();

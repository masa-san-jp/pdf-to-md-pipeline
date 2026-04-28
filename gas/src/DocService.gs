/**
 * Google Doc の生成・命名を担当するサービス。
 */
var DocService = (function () {

  /**
   * 今日の日付を yyyymmdd 形式で返す。
   * @returns {string}
   */
  function generateDatePrefix() {
    var now = new Date();
    var yyyy = now.getFullYear();
    var mm = String(now.getMonth() + 1).padStart(2, '0');
    var dd = String(now.getDate()).padStart(2, '0');
    return '' + yyyy + mm + dd;
  }

  /**
   * ファイル名として使用できない文字を除去する。
   * @param {string} name
   * @returns {string}
   */
  function sanitizeFileName(name) {
    return name
      .replace(/[/\\:*?"<>|]/g, '_') // OS禁則文字
      .replace(/\s+/g, '_')           // 空白
      .replace(/_+/g, '_')            // 連続アンダースコア
      .replace(/^_|_$/g, '')          // 先頭末尾のアンダースコア
      .slice(0, 80);                  // 全体の最大長
  }

  /**
   * 日付プレフィックスとコンテンツ由来名を結合してドキュメント名を生成する。
   * @param {string} contentName - Geminiが提案したファイル名（日付除く）
   * @returns {string} 例: 20260428_請求書_ABC社_4月分
   */
  function buildDocName(contentName) {
    var sanitizedName = sanitizeFileName(contentName);
    var safeName = sanitizedName || 'untitled';
    return generateDatePrefix() + '_' + safeName;
  }

  /**
   * Markdownテキストを本文に持つ Google Doc を作成して指定フォルダに移動する。
   * @param {string} docName - ドキュメント名
   * @param {string} markdownContent - 本文（Markdown形式のプレーンテキスト）
   * @param {Folder} outputFolder - 保存先フォルダ
   * @returns {string} 作成したDocのID
   */
  function createDoc(docName, markdownContent, outputFolder) {
    var doc = DocumentApp.create(docName);
    doc.getBody().setText(markdownContent);
    doc.saveAndClose();

    var file = DriveApp.getFileById(doc.getId());
    file.moveTo(outputFolder);

    return doc.getId();
  }

  return {
    generateDatePrefix: generateDatePrefix,
    sanitizeFileName:   sanitizeFileName,
    buildDocName:       buildDocName,
    createDoc:          createDoc,
  };
})();

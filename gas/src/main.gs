/**
 * メインエントリポイント。
 * Google Apps Script のタイムドリガー（10分ごと推奨）から呼び出す。
 */

/**
 * 入力フォルダ内のファイルをOCR処理してGoogle Docを生成する。
 * - タイムアウト（5分）・最大件数（10件/回）で処理量を制御
 * - 処理済みファイルは FOLDER_ID_PROCESSED へ移動、名前を Doc と揃える
 * - エラーファイルは FOLDER_ID_ERROR へ退避
 */
function processDocuments() {
  var lock = LockService.getScriptLock();
  if (!lock.tryLock(1000)) {
    Logger.log('別の processDocuments 実行中のため、今回の実行はスキップします。');
    return;
  }

  try {
    var startTime = Date.now();

    var inputFolder     = DriveApp.getFolderById(CONFIG.FOLDER_ID_INPUT);
    var processedFolder = DriveApp.getFolderById(CONFIG.FOLDER_ID_PROCESSED);
    var errorFolder     = DriveApp.getFolderById(CONFIG.FOLDER_ID_ERROR);
    var outputFolder    = DriveApp.getFolderById(CONFIG.FOLDER_ID_OUTPUT);

    var files = inputFolder.getFiles();
    var processedCount = 0;

    while (files.hasNext()) {
      if (Date.now() - startTime >= CONFIG.TIMEOUT_MS) {
        Logger.log('タイムアウト。次回の実行で残りファイルを処理します。');
        break;
      }
      if (processedCount >= CONFIG.MAX_FILES_PER_RUN) {
        Logger.log('最大処理件数に達しました: ' + CONFIG.MAX_FILES_PER_RUN);
        break;
      }

      var file = files.next();
      var mimeType = file.getMimeType();

      if (CONFIG.SUPPORTED_MIME_TYPES.indexOf(mimeType) === -1) {
        Logger.log('非対応ファイルをスキップ: ' + file.getName() + ' (' + mimeType + ')');
        continue;
      }

      try {
        var base64Data = Utilities.base64Encode(file.getBlob().getBytes());
        var result = GeminiService.extract(base64Data, mimeType);

        if (!result) {
          Logger.log('OCR失敗、エラーフォルダへ退避: ' + file.getName());
          file.moveTo(errorFolder);
          continue;
        }

        var docName = DocService.buildDocName(result.filename);

        // Google Doc を作成
        DocService.createDoc(docName, result.content, outputFolder);

        // 入力ファイルをリネームして処理済みフォルダへ移動
        var ext = _getExtension(file.getName());
        file.setName(docName + ext);
        file.moveTo(processedFolder);

        Logger.log('完了: ' + docName);
        processedCount++;

      } catch (e) {
        Logger.log('エラー [' + file.getName() + ']: ' + e.toString());
        try { file.moveTo(errorFolder); } catch (_) {}
      }
    }

    Logger.log('処理完了: ' + processedCount + '件');
  } finally {
    lock.releaseLock();
  }
}

/**
 * ファイル名から拡張子を取得する。
 * @param {string} fileName
 * @returns {string} 例: ".pdf", ".jpg"。拡張子なしの場合は空文字。
 */
function _getExtension(fileName) {
  var idx = fileName.lastIndexOf('.');
  return idx !== -1 ? fileName.slice(idx) : '';
}

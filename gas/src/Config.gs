/**
 * 設定オブジェクト。全定数はここで一元管理する。
 * APIキーはスクリプトプロパティ（[ファイル] > [プロジェクトのプロパティ]）に保存し、
 * コードには絶対に直書きしない。
 */
var CONFIG = {
  // Google Drive フォルダID
  FOLDER_ID_INPUT:     PropertiesService.getScriptProperties().getProperty('FOLDER_ID_INPUT'),
  FOLDER_ID_PROCESSED: PropertiesService.getScriptProperties().getProperty('FOLDER_ID_PROCESSED'),
  FOLDER_ID_ERROR:     PropertiesService.getScriptProperties().getProperty('FOLDER_ID_ERROR'),
  FOLDER_ID_OUTPUT:    PropertiesService.getScriptProperties().getProperty('FOLDER_ID_OUTPUT'),

  // Gemini API
  GEMINI_API_KEY: PropertiesService.getScriptProperties().getProperty('GEMINI_API_KEY'),
  GEMINI_MODEL:   'gemini-2.5-flash',

  // 処理制御
  TIMEOUT_MS:        5 * 60 * 1000, // 5分（GAS上限6分に対する安全マージン）
  MAX_FILES_PER_RUN: 10,

  // 対応MIMEタイプ
  SUPPORTED_MIME_TYPES: [
    'image/jpeg',
    'image/png',
    'image/tiff',
    'image/heic',
    'image/heif',
    'image/webp',
    'application/pdf',
  ],
};

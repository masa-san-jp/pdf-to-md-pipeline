/* eslint-disable no-eval */
const fs = require('fs');
const path = require('path');

// ---- GAS グローバルモック ------------------------------------------------

global.Logger = { log: jest.fn() };
global.UrlFetchApp = { fetch: jest.fn() };
global.DriveApp = { getFolderById: jest.fn(), getFileById: jest.fn() };
global.DocumentApp = { create: jest.fn() };
global.Utilities = { base64Encode: jest.fn() };

// Config.gs は PropertiesService を最上位で呼ぶため、テスト時は直接モックで代替
var CONFIG = { // eslint-disable-line no-var
  FOLDER_ID_INPUT:     'test-folder-input',
  FOLDER_ID_PROCESSED: 'test-folder-processed',
  FOLDER_ID_ERROR:     'test-folder-error',
  FOLDER_ID_OUTPUT:    'test-folder-output',
  GEMINI_API_KEY:      'test-api-key',
  GEMINI_MODEL:        'gemini-2.5-flash',
  TIMEOUT_MS:          5 * 60 * 1000,
  MAX_FILES_PER_RUN:   10,
  SUPPORTED_MIME_TYPES: [
    'image/jpeg', 'image/png', 'image/tiff',
    'image/heic', 'image/heif', 'image/webp', 'application/pdf',
  ],
};

// ---- GASファイルをトップレベルで eval（var 宣言をこのスコープに展開）------

eval(fs.readFileSync(path.join(__dirname, '../src/DocService.gs'), 'utf8'));
eval(fs.readFileSync(path.join(__dirname, '../src/GeminiService.gs'), 'utf8'));
eval(fs.readFileSync(path.join(__dirname, '../src/main.gs'), 'utf8'));

// ---- テスト ---------------------------------------------------------------

describe('DocService', () => {
  describe('generateDatePrefix', () => {
    it('yyyymmdd 形式（8桁）を返す', () => {
      expect(DocService.generateDatePrefix()).toMatch(/^\d{8}$/);
    });

    it('今日の年月日と一致する', () => {
      const now = new Date();
      const expected =
        String(now.getFullYear()) +
        String(now.getMonth() + 1).padStart(2, '0') +
        String(now.getDate()).padStart(2, '0');
      expect(DocService.generateDatePrefix()).toBe(expected);
    });
  });

  describe('sanitizeFileName', () => {
    it('OS禁則文字をアンダースコアに置換する', () => {
      expect(DocService.sanitizeFileName('ファイル/名:前')).toBe('ファイル_名_前');
    });

    it('空白をアンダースコアに置換する', () => {
      expect(DocService.sanitizeFileName('foo bar baz')).toBe('foo_bar_baz');
    });

    it('連続するアンダースコアを1つに圧縮する', () => {
      expect(DocService.sanitizeFileName('foo__bar___baz')).toBe('foo_bar_baz');
    });

    it('先頭・末尾のアンダースコアを除去する', () => {
      expect(DocService.sanitizeFileName('_foo_')).toBe('foo');
    });

    it('日本語ファイル名はそのまま保持する', () => {
      expect(DocService.sanitizeFileName('請求書_ABC社_4月分')).toBe('請求書_ABC社_4月分');
    });

    it('80文字を超える場合は切り詰める', () => {
      const long = 'あ'.repeat(100);
      expect(DocService.sanitizeFileName(long).length).toBeLessThanOrEqual(80);
    });
  });

  describe('buildDocName', () => {
    it('yyyymmdd_<name> の形式になる', () => {
      expect(DocService.buildDocName('請求書_ABC社')).toMatch(/^\d{8}_請求書_ABC社$/);
    });

    it('禁則文字を含むコンテンツ名もサニタイズされる', () => {
      expect(DocService.buildDocName('foo/bar')).toMatch(/^\d{8}_foo_bar$/);
    });
  });

  describe('createDoc', () => {
    it('DocumentApp.create を呼び出し、ファイルを outputFolder へ移動する', () => {
      const mockFile = { moveTo: jest.fn() };
      const mockBody = { setText: jest.fn() };
      const mockDoc = {
        getBody: () => mockBody,
        saveAndClose: jest.fn(),
        getId: () => 'doc-id-123',
      };
      const mockFolder = {};

      DocumentApp.create.mockReturnValue(mockDoc);
      DriveApp.getFileById.mockReturnValue(mockFile);

      const id = DocService.createDoc('20260428_テスト文書', '# テスト\n内容', mockFolder);

      expect(DocumentApp.create).toHaveBeenCalledWith('20260428_テスト文書');
      expect(mockBody.setText).toHaveBeenCalledWith('# テスト\n内容');
      expect(mockFile.moveTo).toHaveBeenCalledWith(mockFolder);
      expect(id).toBe('doc-id-123');
    });
  });
});

describe('GeminiService', () => {
  beforeEach(() => jest.clearAllMocks());

  it('正常レスポンスから filename と content を返す', () => {
    const payload = { filename: '請求書_テスト', content: '# 請求書\n金額: 10000円' };
    UrlFetchApp.fetch.mockReturnValue({
      getResponseCode: () => 200,
      getContentText: () => JSON.stringify({
        candidates: [{ content: { parts: [{ text: JSON.stringify(payload) }] } }],
      }),
    });

    expect(GeminiService.extract('base64data', 'image/jpeg')).toEqual(payload);
  });

  it('モデルがコードブロックで囲んだ場合もパースできる', () => {
    const payload = { filename: '契約書_XYZ社', content: '# 契約書\n...' };
    UrlFetchApp.fetch.mockReturnValue({
      getResponseCode: () => 200,
      getContentText: () => JSON.stringify({
        candidates: [{ content: { parts: [{ text: '```json\n' + JSON.stringify(payload) + '\n```' }] } }],
      }),
    });

    expect(GeminiService.extract('base64data', 'application/pdf')).toEqual(payload);
  });

  it('HTTPエラー時は null を返す', () => {
    UrlFetchApp.fetch.mockReturnValue({
      getResponseCode: () => 500,
      getContentText: () => 'Internal Server Error',
    });

    expect(GeminiService.extract('base64data', 'image/png')).toBeNull();
  });

  it('filename または content が欠落している場合は null を返す', () => {
    UrlFetchApp.fetch.mockReturnValue({
      getResponseCode: () => 200,
      getContentText: () => JSON.stringify({
        candidates: [{ content: { parts: [{ text: '{"filename":"foo"}' }] } }],
      }),
    });

    expect(GeminiService.extract('base64data', 'image/jpeg')).toBeNull();
  });

  it('不正なJSONは null を返す', () => {
    UrlFetchApp.fetch.mockReturnValue({
      getResponseCode: () => 200,
      getContentText: () => JSON.stringify({
        candidates: [{ content: { parts: [{ text: 'not json' }] } }],
      }),
    });

    expect(GeminiService.extract('base64data', 'image/jpeg')).toBeNull();
  });
});

describe('_getExtension', () => {
  it('.pdf を返す', () => { expect(_getExtension('doc.pdf')).toBe('.pdf'); });
  it('.jpg を返す', () => { expect(_getExtension('photo.jpg')).toBe('.jpg'); });
  it('拡張子なしは空文字を返す', () => { expect(_getExtension('noext')).toBe(''); });
  it('複数ドットのファイルは最後の拡張子を返す', () => {
    expect(_getExtension('archive.tar.gz')).toBe('.gz');
  });
});

describe('CONFIG', () => {
  it('SUPPORTED_MIME_TYPES に PDF と主要画像形式が含まれる', () => {
    expect(CONFIG.SUPPORTED_MIME_TYPES).toContain('application/pdf');
    expect(CONFIG.SUPPORTED_MIME_TYPES).toContain('image/jpeg');
    expect(CONFIG.SUPPORTED_MIME_TYPES).toContain('image/png');
  });
});

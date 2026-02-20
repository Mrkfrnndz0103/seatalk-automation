# Google Apps Script Dashboard Export (No External API)

This flow runs entirely in Google Apps Script:

1. Watch `config!B2`
2. When it changes to `Updated`, export `dashboard_summary!B2:AD43` as PDF
3. Convert PDF to PNG using Google Drive thumbnail (first page)
4. Send text + image to SeaTalk webhook

Quick copy source file: `scripts/apps_script/dashboard_export.gs`

## 1. Apps Script code

Create a bound script from your target spreadsheet and paste:

```javascript
const CFG = {
  triggerSheet: "config",
  triggerCell: "B2",
  triggerValue: "Updated",
  dashboardSheet: "dashboard_summary",
  dashboardRange: "B2:AD43",
  seatalkWebhookUrl: "https://openapi.seatalk.io/webhook/group/REPLACE_ME",
  atAll: true,
  textTemplate: "Outbound Stuck at SOC_Staging Stuckup Validation Report {date}",
  dateFormat: "yyyy-MM-dd",
  stateKey: "dashboard_alert_last_trigger_value"
};

function onEdit(e) {
  // Installable onEdit trigger is required (simple trigger won't have full auth).
  if (!e || !e.range) return;
  const sheet = e.range.getSheet();
  if (sheet.getName() !== CFG.triggerSheet) return;
  if (e.range.getA1Notation() !== CFG.triggerCell) return;
  processDashboardTrigger_();
}

function processDashboardTrigger_() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const cfgSheet = ss.getSheetByName(CFG.triggerSheet);
  const current = String(cfgSheet.getRange(CFG.triggerCell).getDisplayValue() || "").trim();
  const currentNorm = current.toLowerCase();
  const targetNorm = CFG.triggerValue.toLowerCase();

  const props = PropertiesService.getScriptProperties();
  const previous = String(props.getProperty(CFG.stateKey) || "");
  const previousNorm = previous.toLowerCase();

  // Gate: send only on transition to Updated.
  if (currentNorm !== targetNorm) {
    props.setProperty(CFG.stateKey, current);
    return;
  }
  if (previousNorm === targetNorm) {
    return;
  }

  const dateText = Utilities.formatDate(new Date(), Session.getScriptTimeZone(), CFG.dateFormat);
  const text = CFG.textTemplate.replace("{date}", dateText);

  const pdfBlob = exportRangeAsPdf_(ss.getId(), CFG.dashboardSheet, CFG.dashboardRange);
  const pngBlob = convertPdfToPngViaDriveThumbnail_(pdfBlob);

  sendSeatalkText_(text, CFG.atAll);
  sendSeatalkImage_(pngBlob);

  props.setProperty(CFG.stateKey, current);
}

function exportRangeAsPdf_(spreadsheetId, sheetName, a1Range) {
  const ss = SpreadsheetApp.openById(spreadsheetId);
  const sheet = ss.getSheetByName(sheetName);
  if (!sheet) throw new Error("Sheet not found: " + sheetName);

  const bounds = parseA1Range_(a1Range); // 0-based inclusive bounds
  const params = {
    format: "pdf",
    gid: sheet.getSheetId(),
    portrait: "false",
    fitw: "true",
    gridlines: "false",
    sheetnames: "false",
    printtitle: "false",
    pagenum: "UNDEFINED",
    fzr: "false",
    r1: bounds.startRow,
    c1: bounds.startCol,
    r2: bounds.endRow + 1,
    c2: bounds.endCol + 1
  };

  const qs = Object.keys(params)
    .map(k => encodeURIComponent(k) + "=" + encodeURIComponent(String(params[k])))
    .join("&");
  const url = "https://docs.google.com/spreadsheets/d/" + spreadsheetId + "/export?" + qs;

  const resp = UrlFetchApp.fetch(url, {
    method: "get",
    headers: { Authorization: "Bearer " + ScriptApp.getOAuthToken() },
    muteHttpExceptions: true
  });
  if (resp.getResponseCode() !== 200) {
    throw new Error("PDF export failed: HTTP " + resp.getResponseCode() + " " + resp.getContentText());
  }

  return resp.getBlob().setName("dashboard_capture.pdf");
}

function convertPdfToPngViaDriveThumbnail_(pdfBlob) {
  // Requires Advanced Google Service: Drive API (v2) enabled.
  const tempFile = DriveApp.createFile(pdfBlob);
  try {
    let thumbnailUrl = "";
    for (var i = 0; i < 5; i++) {
      const meta = Drive.Files.get(tempFile.getId(), { fields: "thumbnailLink" });
      thumbnailUrl = (meta && meta.thumbnailLink) ? meta.thumbnailLink : "";
      if (thumbnailUrl) break;
      Utilities.sleep(1000);
    }
    if (!thumbnailUrl) throw new Error("Drive thumbnailLink not available for exported PDF");

    // Request larger thumbnail size if available.
    thumbnailUrl = thumbnailUrl.replace(/=s\d+/, "=s2048");

    const thumbResp = UrlFetchApp.fetch(thumbnailUrl, {
      method: "get",
      headers: { Authorization: "Bearer " + ScriptApp.getOAuthToken() },
      muteHttpExceptions: true
    });
    if (thumbResp.getResponseCode() !== 200) {
      throw new Error("PNG fetch failed: HTTP " + thumbResp.getResponseCode() + " " + thumbResp.getContentText());
    }

    return thumbResp.getBlob().setName("dashboard_capture.png");
  } finally {
    tempFile.setTrashed(true);
  }
}

function sendSeatalkText_(content, atAll) {
  const payload = {
    tag: "text",
    text: {
      content: content,
      at_all: !!atAll
    }
  };
  postSeatalk_(payload);
}

function sendSeatalkImage_(pngBlob) {
  const base64 = Utilities.base64Encode(pngBlob.getBytes());
  let payload = {
    tag: "image",
    image_base64: {
      content: base64
    }
  };

  let resp = postSeatalk_(payload, true);
  if (resp && resp.code && resp.code !== 0) {
    // Fallback shape used by some webhook variants.
    payload = {
      tag: "image",
      image: {
        content: base64
      }
    };
    postSeatalk_(payload);
  }
}

function postSeatalk_(payload, muteErrors) {
  const resp = UrlFetchApp.fetch(CFG.seatalkWebhookUrl, {
    method: "post",
    contentType: "application/json",
    payload: JSON.stringify(payload),
    muteHttpExceptions: true
  });

  const code = resp.getResponseCode();
  const text = resp.getContentText();
  if (code < 200 || code >= 300) {
    if (!muteErrors) throw new Error("SeaTalk webhook failed: HTTP " + code + " " + text);
    return null;
  }
  try {
    return JSON.parse(text);
  } catch (err) {
    return { raw: text };
  }
}

function parseA1Range_(a1) {
  const clean = String(a1).replace(/\$/g, "");
  const parts = clean.split(":");
  if (parts.length !== 2) throw new Error("Range must be bounded, e.g. B2:AD43");
  const start = parseA1Cell_(parts[0]);
  const end = parseA1Cell_(parts[1]);
  if (end.row < start.row || end.col < start.col) throw new Error("Invalid range bounds: " + a1);
  return { startRow: start.row, startCol: start.col, endRow: end.row, endCol: end.col };
}

function parseA1Cell_(ref) {
  const m = String(ref).trim().match(/^([A-Za-z]+)(\d+)$/);
  if (!m) throw new Error("Invalid A1 cell: " + ref);
  const letters = m[1].toUpperCase();
  const row = Number(m[2]) - 1;
  let col = 0;
  for (var i = 0; i < letters.length; i++) {
    col = col * 26 + (letters.charCodeAt(i) - 64);
  }
  return { row: row, col: col - 1 };
}
```

## 2. Enable required services

1. In Apps Script editor: `Services` -> add `Drive API` (advanced service).
2. In Google Cloud project for this script, ensure Drive API is enabled.

## 3. Create installable trigger

1. In Apps Script editor: `Triggers` -> `Add Trigger`
2. Function: `onEdit`
3. Event source: `From spreadsheet`
4. Event type: `On edit`

## 4. Notes

- This is fully Google-native: Sheets + Drive + Apps Script + UrlFetch.
- PNG uses Drive thumbnail of exported PDF (first page).
- It sends once per transition to `Updated` and waits for value to change away before sending again.

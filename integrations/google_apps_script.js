/*
 * Deploy this as a Google Apps Script web app bound to the target spreadsheet.
 * Protect the deployment appropriately before setting GOOGLE_SHEETS_WEBHOOK_URL.
 */
function doPost(event) {
  const payload = JSON.parse(event.postData.contents);
  Object.entries(payload.tabs).forEach(([tabName, tab]) => {
    const sheet = SpreadsheetApp.getActiveSpreadsheet().getSheetByName(tabName);
    if (!sheet) throw new Error(`Missing required tab: ${tabName}`);
    sheet.clearContents();
    sheet.getRange(1, 1, 1, tab.headers.length).setValues([tab.headers]);
    if (tab.rows.length) sheet.getRange(2, 1, tab.rows.length, tab.headers.length).setValues(tab.rows);
  });
  return ContentService
    .createTextOutput(JSON.stringify({ ok: true, tabs: Object.keys(payload.tabs) }))
    .setMimeType(ContentService.MimeType.JSON);
}

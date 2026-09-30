import { test } from "node:test";
import assert from "node:assert/strict";
import { importQueue, mergeScan, syncStatuses, switchVariants } from "../extension/model.js";

const catalog = number => ({ video: `D:\\episodes\\A${number}\\[Full] video.mp4`, tieu_de: `Video ${number}`, variants: {
  dai: `D:\\episodes\\A${number}\\[Full] video.mp4`, nua: `D:\\episodes\\A${number}\\Full ở video.mp4`, ngan: `D:\\episodes\\A${number}\\short.mp4`,
} });
test("JSON status and notes sync without overwriting extension outcomes or receipts", () => {
  const rows = importQueue([catalog(120), catalog(121), catalog(122)]);
  rows[1].trang_thai = "done"; rows[1].statusOrigin = "local";
  rows[2].trang_thai = "đã đăng"; rows[2].statusOrigin = "receipt";
  const source = { muc: rows.map(row => ({ ...row, trang_thai: "lỗi lịch", ghi_chu: "Lịch không hợp lệ" })) };
  assert.equal(syncStatuses(rows, source), 1);
  assert.equal(rows[0].trang_thai, "lỗi lịch");
  assert.equal(rows[0].ghi_chu, "Lịch không hợp lệ");
  assert.equal(rows[1].trang_thai, "done");
  assert.equal(rows[2].trang_thai, "đã đăng");
  source.muc[0].trang_thai = "đã hẹn giờ";
  assert.equal(syncStatuses(rows, source), 1);
  assert.equal(rows[0].trang_thai, "đã hẹn giờ");
  assert.equal(syncStatuses(rows, source), 0);
});
test("bulk variant switch persists through scanning and keeps status, captions and dates", () => {
  const available = importQueue([catalog(120), catalog(121)]);
  const rows = importQueue([catalog(120), catalog(121), catalog(122)]);
  rows[0].gio_dang = "2026-10-01T20:00"; rows[0].trang_thai = "đã hẹn giờ";
  const result = switchVariants(rows, rows.map(row => row.id), "nua", available);
  assert.equal(result.changed, 2); assert.equal(result.missing.length, 1);
  assert.equal(rows[0].video, available[0].variants.nua);
  assert.equal(rows[0].gio_dang, "2026-10-01T20:00");
  assert.equal(rows[0].trang_thai, "đã hẹn giờ");
  mergeScan(rows, available);
  assert.equal(rows[0].video, available[0].variants.nua);
  assert.equal(switchVariants(rows, [rows[0].id], "dai", available).changed, 1);
  assert.equal(rows[0].video, available[0].variants.dai);
  assert.equal(rows[1].video, available[1].variants.nua);
});

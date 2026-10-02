import { test } from "node:test";
import assert from "node:assert/strict";
import { syncSchedule } from "../extension/schedule.js";

const now = new Date("2026-09-29T16:00");
const row = (number, time = "") => ({
  id: String(number), video: `D:\\episodes\\A${number}\\[Full] video.mp4`,
  hashtag: `#MimiAudioSo${number}`, gio_dang: time, trang_thai: "cho",
});
const source = () => ({ khung_gio: "08:00, 20:00", muc: [row(118, "2026-09-30T08:00"), row(124, "2026-10-02T20:00")] });

test("restore JSON dates by folder and give every unposted episode, even an older number, the next slots", () => {
  const rows = [row(105), row(118), row(124), row(126), row(125)];
  rows[2].video = "D:/episodes/A124/short.mp4";
  const result = syncSchedule(rows, source(), now);
  assert.equal(result.restored, 2);
  assert.equal(rows[1].gio_dang, "2026-09-30T08:00");
  assert.equal(rows[2].gio_dang, "2026-10-02T20:00");
  assert.equal(rows[0].gio_dang, "2026-10-03T08:00");
  assert.equal(rows[4].gio_dang, "2026-10-03T20:00");
  assert.equal(rows[3].gio_dang, "2026-10-04T08:00");
  assert.equal(syncSchedule(rows, source(), now).changed, 0);
});
test("a remade old episode and stale past plans move after the latest schedule; ready videos go first", () => {
  const later = new Date("2026-10-02T18:00");
  const rows = [row(113), row(117), row(119), row(125)];
  rows[0].video = ""; rows[2].video = "";
  rows[1].gio_dang = "2026-09-29T08:00"; rows[1].scheduleKind = "manual";
  const data = { khung_gio: "08:00, 20:00", muc: [row(124, "2026-10-02T20:00"), { ...row(119), gio_dang: "2026-09-30T20:00" }] };
  const result = syncSchedule(rows, data, later);
  assert.equal(result.anchor, "2026-10-02T20:00");
  assert.equal(result.restored, 0, "a past JSON plan is not restored");
  assert.deepEqual(rows.map(item => item.gio_dang), ["2026-10-04T08:00", "2026-10-03T08:00", "2026-10-04T20:00", "2026-10-03T20:00"]);
  rows[0].video = "D:\episodes\A113\[Full] video.mp4";
  syncSchedule(rows, data, later);
  assert.deepEqual(rows.map(item => item.gio_dang), ["2026-10-03T08:00", "2026-10-03T20:00", "2026-10-04T20:00", "2026-10-04T08:00"]);
  rows[1].trang_thai = "đã lên lịch";
  syncSchedule(rows, data, later);
  assert.equal(rows[1].gio_dang, "2026-10-03T20:00", "a posted row keeps its time and becomes the anchor");
  assert.deepEqual([rows[0], rows[3], rows[2]].map(item => item.gio_dang), ["2026-10-04T08:00", "2026-10-04T20:00", "2026-10-05T08:00"]);
});
test("use JSON anchors even when the previous video is absent", () => {
  const rows = [row(125)];
  syncSchedule(rows, source(), now);
  assert.equal(rows[0].gio_dang, "2026-10-03T08:00");
});
test("JSON changes reflow generated schedules without overwriting manual times", () => {
  const rows = [row(124), row(125), row(126)];
  const data = source();
  syncSchedule(rows, data, now);
  data.muc[1].gio_dang = "2026-10-04T20:00";
  syncSchedule(rows, data, now);
  assert.equal(rows[0].gio_dang, "2026-10-04T20:00");
  assert.equal(rows[1].gio_dang, "2026-10-05T08:00");
  rows[1].gio_dang = "2026-10-06T20:00";
  rows[1].scheduleKind = "manual";
  syncSchedule(rows, data, now);
  assert.equal(rows[1].gio_dang, "2026-10-06T20:00");
  assert.equal(rows[2].gio_dang, "2026-10-07T08:00");
});
test("preserve existing manual and reviewed dates", () => {
  const rows = [row(124, "2026-10-05T20:00"), row(125, "2026-10-06T08:00"), row(126)];
  rows[1].trang_thai = "review";
  rows[1].scheduleKind = "auto";
  syncSchedule(rows, source(), now);
  assert.equal(rows[0].gio_dang, "2026-10-05T20:00");
  assert.equal(rows[1].gio_dang, "2026-10-06T08:00");
  assert.equal(rows[2].gio_dang, "2026-10-06T20:00");
});
test("roll over year and skip times too near the present", () => {
  const rows = [row(125), row(126)];
  syncSchedule(rows, { khung_gio: "08:00, 20:00", muc: [row(124, "2026-12-31T20:00")] }, new Date("2027-01-01T07:50"));
  assert.equal(rows[0].gio_dang, "2027-01-01T20:00");
  assert.equal(rows[1].gio_dang, "2027-01-02T08:00");
});
test("do not invent a baseline or schedule outside the planning horizon", () => {
  const rows = [row(125)];
  assert.match(syncSchedule(rows, { khung_gio: "08:00", muc: [] }, now).notes[0], /Chưa có giờ đăng/);
  assert.equal(rows[0].gio_dang, "");
  const result = syncSchedule(rows, { khung_gio: "08:00", muc: [row(124, "2026-10-29T20:00")] }, now);
  assert.equal(rows[0].gio_dang, "");
  assert.match(result.notes[0], /30 ngày/);
});
test("missing slots inherit anchor time and invalid dates are ignored", () => {
  const rows = [row(125)];
  syncSchedule(rows, { muc: [row(123, "2026-02-30T20:00"), row(124, "2026-10-02T08:00")] }, now);
  assert.equal(rows[0].gio_dang, "2026-10-03T08:00");
});
test("a manual time moves the generated slots after it without a duplicate", () => {
  const rows = [row(125), row(126)];
  syncSchedule(rows, source(), now);
  rows[1].gio_dang = rows[0].gio_dang;
  rows[1].scheduleKind = "manual";
  const result = syncSchedule(rows, source(), now);
  assert.equal(rows[1].gio_dang, "2026-10-03T08:00");
  assert.equal(rows[0].gio_dang, "2026-10-03T20:00");
  assert.equal(result.notes.length, 0);
});

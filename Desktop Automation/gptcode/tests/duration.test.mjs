import { test } from "node:test";
import assert from "node:assert/strict";
import { importQueue, mergeScan, switchVariants, chooseVariant, videoDuration, formatDuration, validateJob, queueSkipReason, dropPosted, rowKey, TIKTOK_MAX_SECONDS } from "../extension/model.js";
import { applyPostList } from "../extension/posts.js";

const folder = number => `D:\\kịch_bản\\A${number} - truyện`;
const full = number => `${folder(number)}\\[Full] Mimi audio Số ${number} - Tên.mp4`;
const half = number => `${folder(number)}\\Full ở Mimi audio Số ${number} - Tên.mp4`;
const scanned = (number, extra = {}) => ({ video: full(number), thu_muc: folder(number), tieu_de: `Full ở Mimi audio Số ${number} | Tên`, hashtag: `#MimiAudioSo${number}`,
  trang_thai: "cho", ghi_chu: "", variants: { dai: full(number), nua: half(number) }, thoi_luong: { dai: 3613, nua: 1807, ngan: 168 }, ...extra });

test("durations travel with rows through import, scans and variant switches", () => {
  const [row] = importQueue([scanned(139, { thoi_luong: { dai: 3613, nua: "x", other: 5 } })]);
  assert.deepEqual(row.thoi_luong, { dai: 3613 });
  assert.equal(videoDuration(row), 3613);
  assert.equal(videoDuration({ ...row, video: "D:\\x\\custom.mp4" }), null, "a custom file has no known length");
  const rows = importQueue([{ ...scanned(139), thoi_luong: {} }]);
  mergeScan(rows, importQueue([scanned(139)]));
  assert.deepEqual(rows[0].thoi_luong, { dai: 3613, nua: 1807, ngan: 168 });
  switchVariants(rows, [rows[0].id], "nua", importQueue([scanned(139, { thoi_luong: { nua: 1800 } })]));
  assert.equal(rows[0].video, half(139));
  assert.equal(videoDuration(rows[0]), 1800);
  assert.equal(formatDuration(3613), "1:00:13");
  assert.equal(formatDuration(1807.4), "30:07");
  assert.equal(formatDuration(59), "0:59");
});

test("a file over sixty minutes is skipped by the queue and refused by validation, the half video runs", () => {
  const [row] = importQueue([scanned(139)]);
  assert.match(queueSkipReason(row), /1:00:13.*60 phút/);
  assert.match(queueSkipReason(row, { repost: true }), /quá 60 phút/);
  assert.throws(() => validateJob(row, false), /quá 60 phút/);
  const ok = { ...row, video: half(139) };
  assert.equal(queueSkipReason(ok), "");
  assert.doesNotThrow(() => validateJob(ok, false));
  assert.equal(queueSkipReason({ ...row, thoi_luong: { dai: TIKTOK_MAX_SECONDS } }), "", "exactly one hour is accepted");
  assert.equal(queueSkipReason({ ...row, thoi_luong: {} }), "", "an unknown length is not a reason to skip");
});

test("a Full file over sixty minutes gives way to the half video on scans and variant switches", () => {
  // The scanner omits a too-long Full from variants but still reports its length.
  const long = scanned(139, { video: half(139), variants: { nua: half(139), ngan: `${folder(139)}\\short.mp4` }, thoi_luong: { dai: 3613, nua: 1807, ngan: 168 } });
  assert.deepEqual(chooseVariant(long, "dai"), { video: half(139), kind: "nua", fallback: true });
  assert.deepEqual(chooseVariant(scanned(139), "dai"), { video: full(139), kind: "dai" });
  assert.equal(chooseVariant(long, "ngan")?.fallback, undefined);
  assert.equal(chooseVariant({ ...long, variants: { ngan: long.variants.ngan } }, "dai"), null, "no half video: nothing to fall back to");
  const rows = importQueue([scanned(139)]);
  rows[0].variantChoice = "dai";
  mergeScan(rows, importQueue([long]));
  assert.equal(rows[0].video, half(139), "a chosen Full that grew past the limit is replaced by the half");
  assert.equal(rows[0].variantChoice, "dai");
  mergeScan(rows, importQueue([scanned(139, { thoi_luong: { dai: 3000, nua: 1500 } })]));
  assert.equal(rows[0].video, full(139), "a shorter remake brings the Full back");
  const result = switchVariants(rows, [rows[0].id], "dai", importQueue([long]));
  assert.equal(rows[0].video, half(139));
  assert.deepEqual(result.fallback, [rows[0].tieu_de]);
  assert.deepEqual(result.missing, []);
});

test("the TikTok judge reports a verdict per row, unknown when the list stopped before the episode", () => {
  const rows = importQueue([scanned(140), scanned(149), scanned(143, { trang_thai: "running" })]);
  const list = { complete: false, readAt: "2026-10-23T18:19:18.032Z",
    posts: [{ id: "1", url: "https://www.tiktok.com/@m/video/1", caption: "Full ở Mimi audio Số 142 | Tên #MimiAudioSo142", stage: "22 tháng 10, 8:00 SA", icons: ["Alarm"] }] };
  const result = applyPostList(rows, list, new Date("2026-10-23T20:00"));
  assert.deepEqual(result.verdicts, { [rows[0].id]: "unknown", [rows[1].id]: "waiting" });
  assert.equal(rows[0].trang_thai, "cho");
  assert.equal(rows[0].ghi_chu, "", "an unread episode is left exactly as it was");
  assert.match(rows[1].ghi_chu, /Chưa thấy trên TikTok/);
  const complete = applyPostList(importQueue([scanned(140)]), { ...list, complete: true }, new Date("2026-10-23T20:00"));
  assert.deepEqual(Object.values(complete.verdicts), ["waiting"]);
});

test("a scan does not bring back episodes TikTok already has, but keeps rows that were listed", () => {
  const old = importQueue([scanned(140, { trang_thai: "đã đăng" }), scanned(141)]);
  const keep = new Set(old.map(row => row.id));
  const rows = [...old, ...importQueue([
    scanned(142, { trang_thai: "đã lên lịch", statusOrigin: "tiktok" }),
    scanned(143, { trang_thai: "đã đăng", statusOrigin: "receipt" }),
    scanned(144, { trang_thai: "done" }),
    scanned(145), scanned(146, { trang_thai: "error" }), scanned(147, { video: "", trang_thai: "chưa có video" }),
  ])];
  const submissions = { [rowKey(scanned(145))]: { state: "success" }, [rowKey(scanned(146))]: { state: "uncertain" } };
  assert.equal(dropPosted(rows, keep, submissions), 4);
  assert.deepEqual(rows.map(row => row.hashtag), ["#MimiAudioSo140", "#MimiAudioSo141", "#MimiAudioSo146", "#MimiAudioSo147"]);
  assert.equal(dropPosted(rows, keep, submissions), 0);
});

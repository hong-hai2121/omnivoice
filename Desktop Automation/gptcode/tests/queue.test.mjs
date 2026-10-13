import { test } from "node:test";
import assert from "node:assert/strict";
import { queueSkipReason, episodeKey, NO_VIDEO } from "../extension/model.js";

const video = "D:\\kịch_bản\\B129 - truyện\\[Full] Mimi audio Số 129 - Tên.mp4";
const ready = { id: "a", video, tieu_de: "Full ở Mimi audio Số 129", hashtag: "#MimiAudioSo129", gio_dang: "2026-10-11T08:00", trang_thai: "cho" };

test("a script without its video is skipped, whatever its status text says", () => {
  assert.equal(queueSkipReason({ ...ready, video: "", trang_thai: NO_VIDEO, thu_muc: "D:\\kịch_bản\\G134 - truyện" }), "chưa có video");
  assert.equal(queueSkipReason({ ...ready, video: "" }), "chưa có video");
  assert.equal(queueSkipReason({ ...ready, trang_thai: NO_VIDEO }), "chưa có video");
  assert.equal(queueSkipReason({ ...ready, video: "", trang_thai: NO_VIDEO }, { repost: true }), "chưa có video");
});
test("rows TikTok already lists or rows with a click receipt wait for an explicit repost", () => {
  const submissions = { [episodeKey(video)]: { state: "uncertain", video } };
  assert.equal(queueSkipReason(ready), "");
  assert.equal(queueSkipReason({ ...ready, trang_thai: "đã lên lịch", statusOrigin: "tiktok" }), "đã đăng / đã lên lịch trên TikTok");
  assert.equal(queueSkipReason({ ...ready, trang_thai: "done" }), "đã đăng / đã lên lịch trên TikTok");
  assert.match(queueSkipReason({ ...ready, trang_thai: "error" }, { submissions }), /biên nhận/);
  assert.match(queueSkipReason({ ...ready, video: video.toUpperCase() }, { submissions }), /biên nhận/);
  assert.equal(queueSkipReason({ ...ready, trang_thai: "error" }, { submissions, repost: true }), "");
  assert.equal(queueSkipReason({ ...ready, trang_thai: "done" }, { repost: true }), "");
});
test("rows waiting, under review or stopped still run; a running row never runs twice", () => {
  for (const trang_thai of ["cho", "review", "stopped", "error", "đã nạp"]) assert.equal(queueSkipReason({ ...ready, trang_thai }), "", trang_thai);
  assert.equal(queueSkipReason({ ...ready, trang_thai: "running" }), "đang chạy");
  assert.equal(queueSkipReason({ ...ready, trang_thai: "đang tải" }, { repost: true }), "đang chạy");
});

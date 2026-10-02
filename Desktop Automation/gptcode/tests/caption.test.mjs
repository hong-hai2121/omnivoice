import { test } from "node:test";
import assert from "node:assert/strict";
import { auditCaption } from "../extension/caption.js";

test("caption audit tolerates hashtag entity spacing and zero-width markers", () => {
  const state = auditCaption({ present: true, text: "Tiếng Việt\u200b#one\u00a0 #two " }, "Tiếng Việt", ["#one", "#two"]);
  assert.equal(state.titleMatches, true); assert.equal(state.tagsMatch, true);
});
test("caption audit distinguishes changed titles from missing or extra hashtags", () => {
  const state = auditCaption({ present: true, text: 'Changed #one #one #wrong' }, 'Original', ['#one', '#two']);
  assert.equal(state.titleMatches, false);
  assert.deepEqual(state.missing, ['#two']);
  assert.deepEqual(state.extra, ['#one', '#wrong']);
  assert.equal(state.tagsMatch, false);
});
test("only a near-identical title is close; an empty, different or mostly missing one is not", async () => {
  const { titleClose } = await import("../extension/caption.js");
  const title = "Full ở Mimi audio Số 117 | Màn Cắt Đứt Tính Cả Nể Của Đứa Con Mới Tròn Mười Tuổi";
  assert.equal(titleClose(title.replace(" | ", " - "), title), true);
  assert.equal(titleClose(title + ".", title), true);
  assert.equal(titleClose("", title), false);
  assert.equal(titleClose("Full ở Mimi audio Số 117", title), false);
  assert.equal(titleClose("[Full] Mimi audio Số 117 - Màn Cắt Đứt Tính Cả Nể Của Đứa Con Mới Tròn Mười Tuổi", title), false);
  assert.equal(titleClose("Changed title", "Test"), false);
  assert.equal(titleClose("", ""), true);
});

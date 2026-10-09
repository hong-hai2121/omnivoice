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
test("caption audit requires the full title, tolerating only Unicode and whitespace differences", () => {
  const title = "Full ở Mimi audio Số 117 | Màn Cắt Đứt Tính Cả Nể Của Đứa Con Mới Tròn Mười Tuổi";
  const matches = text => auditCaption({ present: true, text }, title, []).titleMatches;
  assert.equal(matches(title.normalize('NFD').replaceAll(' ', '\u00a0  ')), true);
  for (const changed of [title.replace(" | ", " - "), title + ".", title.slice(0, -5), '', 'Changed title']) {
    assert.equal(matches(changed), false);
  }
});

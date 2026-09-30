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

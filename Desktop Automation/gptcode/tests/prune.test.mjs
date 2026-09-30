import { test } from "node:test";
import assert from "node:assert/strict";
import { pruneMissingFolders } from "../extension/model.js";

const root = "D:\\myvoice\\kich_ban";
const inventory = folders => ({ ok: true, root, folders_complete: true, folders: folders.map(name => root + "\\" + name), muc: [] });

test("prune deleted episode folders including imported and completed rows, preserving unrelated paths", () => {
  const rows = [
    { id: "gone", video: root + "\\A100\\full.mp4", trang_thai: "done" },
    { id: "exists", video: "d:/MYVOICE/kich_ban/A101/full.mp4", variantChoice: "nua", gio_dang: "2026-10-02T20:00" },
    { id: "nested", video: root + "\\A101\\sub\\file.mp4" },
    { id: "external", video: "E:\\manual\\file.mp4" },
    { id: "sibling", video: root + "_backup\\A100\\file.mp4" },
    { id: "draft", video: "" },
  ];
  assert.equal(pruneMissingFolders(rows, inventory(["A101"])), 1);
  assert.deepEqual(rows.map(row => row.id), ["exists", "nested", "external", "sibling", "draft"]);
  assert.equal(rows[0].gio_dang, "2026-10-02T20:00");
  assert.equal(pruneMissingFolders(rows, inventory(["A101"])), 0);
});

test("absent, incomplete, invalid or failed inventories never remove rows", () => {
  for (const scan of [undefined, { ok: true, root, muc: [] }, { ...inventory([]), folders_complete: false },
    { ...inventory([]), ok: false }, { ...inventory([]), folders: [null] },
    { ...inventory([]), folders: ["E:\\outside"] }, { ...inventory([]), root: "relative" }]) {
    const rows = [{ video: root + "\\A100\\file.mp4" }];
    assert.equal(pruneMissingFolders(rows, scan), 0);
    assert.equal(rows.length, 1);
  }
});

test("a valid empty folder inventory removes only rows under the scanned root", () => {
  const rows = [{ video: root + "\\A100\\file.mp4" }, { video: "E:\\other\\file.mp4" }];
  assert.equal(pruneMissingFolders(rows, inventory([])), 1);
  assert.equal(rows[0].video, "E:\\other\\file.mp4");
});

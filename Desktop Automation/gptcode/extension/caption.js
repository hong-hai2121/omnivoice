export const captionText = value => String(value || "").normalize("NFC")
  .replace(/[\u200b-\u200d\ufeff]/g, "").replace(/\s+/g, " ").trim();

export function auditCaption(snapshot, title, expectedTags) {
  const text = captionText(snapshot?.text);
  const pattern = /#[\p{L}\p{M}\p{N}_]+/gu;
  const actualTags = text.match(pattern) || [];
  const remaining = [...actualTags];
  const missing = [];
  for (const tag of expectedTags.map(captionText)) {
    const index = remaining.indexOf(tag);
    if (index < 0) missing.push(tag);
    else remaining.splice(index, 1);
  }
  const actualTitle = captionText(text.replace(pattern, " "));
  return { present: !!snapshot?.present, actualTitle, actualTags, missing, extra: remaining,
    titleMatches: actualTitle === captionText(title), titleClose: titleClose(actualTitle, title),
    tagsMatch: !missing.length && !remaining.length };
}

// Same title apart from spacing/punctuation (or a slightly trimmed copy). An empty or
// different title is never close, so it can never be published on a mere warning.
export function titleClose(actual, expected) {
  const core = value => captionText(value).toLocaleLowerCase("vi").replace(/[^\p{L}\p{M}\p{N}]+/gu, "");
  const a = core(actual), e = core(expected);
  if (!a || !e) return a === e;
  if (a === e) return true;
  return (a.includes(e) || e.includes(a)) && Math.min(a.length, e.length) / Math.max(a.length, e.length) >= 0.8;
}

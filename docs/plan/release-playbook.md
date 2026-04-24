# openclaw-agent-dashboard 发布流程

> 版本号需同时修改两个文件：根 `package.json` 和 `plugin/package.json`

## 发布步骤

### Step 1 — 升版本号 + 提交 + 打 tag
```bash
cd /home/umarchen/openclaw-agent-dashboard-new

# 修改版本号（两个文件）
sed -i 's/"version": "{OLD_VERSION}"/"version": "{NEW_VERSION}"/' package.json
sed -i 's/"version": "{OLD_VERSION}"/"version": "{NEW_VERSION}"/' plugin/package.json

# 确认
grep '"version"' package.json | head -1
grep '"version"' plugin/package.json | head -1

# 提交（commit message 根据实际改动内容编写）
git add -A
git commit -m "fix: release {NEW_VERSION} — {改动摘要}"
git tag v{NEW_VERSION}
```

### Step 2 — 推送 Git + GitHub Release
```bash
git push origin main
git push origin v{NEW_VERSION}
gh release create v{NEW_VERSION} \
  --title "v{NEW_VERSION}" \
  --notes "### Changes
- 改动1
- 改动2"
```

### Step 3 — npm 发布
```bash
npm run pack
cd plugin && npm publish --access public
```

### Step 4 — 回写根 package.json 自依赖
```bash
cd ..
sed -i 's/"openclaw-agent-dashboard": "\^{OLD_VERSION}"/"openclaw-agent-dashboard": "^{NEW_VERSION}"/' package.json
git add package.json
git commit -m "chore: root package.json 自依赖改为 ^{NEW_VERSION}（发布后）"
git push origin main
```

## 注意事项
- commit message 根据具体修改内容编写，描述清楚改了什么
- npm token 已配置在 `~/.npmrc`，当前 token 带 publish 权限，无需 OTP
- 如果 token 失效，需要到 npmjs.com 重新生成 Granular Access Token（Read and write）

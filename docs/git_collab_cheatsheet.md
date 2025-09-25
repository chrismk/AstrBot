## Git 协作流程速查表（Fork + Upstream）

适用场景：你已 fork 上游仓库（AstrBotDevs/AstrBot），本地开发在自己的 fork 上进行，通过 PR（可选）或仅自用同步上游。

---

### 术语
- **origin**：你的 fork 远端（如 `github.com/chrismk/AstrBot`）
- **upstream**：上游原始仓库（`github.com/AstrBotDevs/AstrBot`）
- 常见主分支：`master` 或 `dev`（请以上游实际为准）

---

### 一次性配置（已完成可跳过）
```bash
# 添加远端（如果尚未添加）
git remote add origin https://github.com/chrismk/AstrBot.git
git remote add upstream https://github.com/AstrBotDevs/AstrBot.git

# 查看远端
git remote -v
```

---

### 常规功能开发流程（建议）
```bash
# 1) 基于本地 main 拉新分支
git checkout main
git pull --ff-only            # 更新 main（从 origin）
git checkout -b feat/your-change

# 2) 编码、提交
git add -A
git commit -m "feat: 描述你的改动"

# 3) 推送到你的 fork
git push -u origin feat/your-change
# 之后同分支仅需：git push

# 4)（可选）在 GitHub 上从 feat/your-change 向上游发起 PR
```

分支命名建议：
- 功能：`feat/xxx`  修复：`fix/xxx`  性能：`perf/xxx`  重构：`refactor/xxx`
- 个人长期分支：`dev/chrismk`（如已存在 `dev/chrismk`）

---

### 仅自用：在个人分支开发并同步上游（不提 PR）

方式 A（推荐，经 main 中转）：
```bash
# 1) 让 main 跟上游一致
git checkout main
git fetch upstream
git merge upstream/master      # 或 upstream/dev（按上游实际）
git push origin main           # 可选：备份到你的 fork

# 2) 把更新并入你的个人分支
git checkout dev/chrismk
git merge main
# 解决冲突 -> git add -A -> git commit（如产生合并提交）
git push                       # 可选：备份
```

方式 B（直接并入上游到个人分支）：
```bash
git checkout dev/chrismk
git fetch upstream
git merge upstream/master      # 或 upstream/dev
# 解决冲突 -> git add -A -> git commit
git push                       # 可选
```

（可选）将本地 main 直接跟踪上游，减少误操作：
```bash
git checkout main
git branch --set-upstream-to=upstream/master   # 或 upstream/dev
# 之后更新 main 只需：
git pull
```

---

### 查看状态与历史
```bash
git status
git branch -vv
git remote -v
git log --oneline --graph --decorate --all
```

---

### 撤销与回滚（常用）
```bash
# 撤销暂存（回到未暂存状态）
git reset HEAD <file>

# 丢弃工作区改动（回到最新提交）
git checkout -- <file>

# 回滚某次提交（生成反向提交）
git revert <commit_sha>
```

---

### 解决冲突（简要）
```bash
# 发生冲突后，编辑文件保留正确内容
git add <file>

# 如果是 merge 流程
git commit

# 如果是 rebase 流程
git rebase --continue
```

---

### Rebase（可选，使历史更线性，协作需谨慎）
```bash
git checkout feat/your-change
git fetch upstream
git rebase upstream/master     # 或 upstream/dev
# 解决冲突 -> git add -A -> git rebase --continue
git push -f                    # rebase 后需强推
```

---

### 小贴士
- 初次 `push` 建议加 `-u` 建立跟踪：`git push -u origin <branch>`
- 日常提交信息风格：`feat:`/`fix:`/`docs:`/`refactor:`/`perf:`/`test:`/`chore:`
- 保持 `main` 干净、可随时更新，开发都在分支上进行

---

维护：如本文档需更新，请直接编辑并提交 PR 或在你的个人分支更新。



# main 分支保护

GitHub Actions 工作流首次在 `main` 成功运行后，在仓库页面进入：

`Settings` → `Rules` → `Rulesets` → `New ruleset` → `New branch ruleset`

创建名为 `Protect main` 的 Active ruleset，并配置：

- Target branches：`Include default branch`。
- Bypass list：`Repository administrators`，模式限定为 `For pull requests only`。
- 启用 `Restrict deletions`。
- 启用 `Block force pushes`。
- 启用 `Require a pull request before merging`：
  - Required approvals：`1`；
  - 启用 `Dismiss stale pull request approvals when new commits are pushed`；
  - 启用 `Require approval of the most recent reviewable push`；
  - 启用 `Require conversation resolution before merging`。
- 启用 `Require status checks to pass before merging`：
  - `Backend / quality`；
  - `Agent / quality`；
  - `Database / migrations`；
  - 启用 `Require branches to be up to date before merging`。

本阶段不启用 Code Owners、signed commits、linear history、merge queue 或 deployment
checks。Required check 名称是分支保护接口；修改 `.github/workflows/ci.yml` 中的 job
名称时，必须同步修改 ruleset。

配置完成后用测试 Pull Request 验证：缺少 approval、任一 CI 失败或存在未解决会话时均
无法合并；推送新提交后旧 approval 失效；普通成员和管理员均不能直接推送 `main`；
管理员只能从已有 Pull Request 使用带审计记录的应急绕过。

GitHub 操作说明：
[Creating rulesets for a repository](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/creating-rulesets-for-a-repository)。


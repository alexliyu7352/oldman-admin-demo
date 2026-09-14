# Oldman Admin Demo

这是内置 `oldman.apps.admin` 的独立运行示例，使用本地 SQLite 和 Redis Session，不依赖 EPG 业务源码。启动前需要有可用的 Redis；默认示例配置使用 `127.0.0.1:6379/5`。Admin 前端仍消费 `oldman-web/dashboard`、共享组件和 `oldman.web` 服务端协议，不维护第二套 UI。

## 安装

```bash
# 前置条件：bootstrap 会直接调用 uv 和 pnpm，先把两者装好
#   uv：       curl -LsSf https://astral.sh/uv/install.sh | sh
#   pnpm：     安装 Node.js 20 及以上后执行 corepack enable
python3 scripts/bootstrap.py
./run.sh web settings init
```

`settings init` 以 `data/web_settings.example.yaml` 为项目配置模板，生成本地
`data/web_settings.yaml`，并补齐默认配置和安全密钥。

仓库与框架源码目录（`oldman_framwork` 或 `oldman`）同级时，bootstrap 自动把 Oldman 源码 editable 安装到本仓库的 `.venv`，并让前端安装使用本地 `oldman-web`。链接和依赖均位于 Git 忽略目录，修改框架 Python 源码后不需要重新构建或安装。

没有同级源码仓库时，同一命令安装 `pyproject.toml` 和 `frontend/package.json` 声明的 PyPI/npm 正式包，因此本仓库可以独立克隆和发布。

## 运行

启动服务前，先同步配置、迁移数据库、按需导入预设项目并创建自己的管理员：

```bash
./run.sh web settings sync
./run.sh db migrate
./run.sh web loaddata demo
./run.sh web createsuperuser
```

然后构建、收集资源并启动：

```bash
pnpm --dir frontend build
./run.sh web static collect
./run.sh web start
```

需要直接调试 Oldman 和 Demo 前端源码时，在上述配置和数据已准备后使用 `python3 scripts/dev.py`。
它统一管理 Web 服务和两个 Vite 服务；内置 Admin 使用 `5173`，Demo 扩展使用 `5174`。
依赖关系不需要人工切换，普通启动仍读取已构建 manifest；不要同时启动两个入口占用同一端口。

以后需要修改密码时运行：

```bash
./run.sh web changepassword oldman_admin
```

将 `oldman_admin` 替换为刚才实际创建的用户名；Demo 不提供默认账号。

打开 <http://127.0.0.1:17999/admin>。服务启动和用户管理命令都不会自动建表，部署时必须先显式执行迁移。

`loaddata demo` 显式导入 `apps/demo/fixtures/demo.json` 的25个真实项目，不创建账号。
正常启动不再重建项目、重置密码或删除用户；修改、删除项目后重启会保留结果。
fixture 的主键是1–25，再次导入会按主键更新这些记录；只在自己的演示数据库使用，不覆盖已有业务数据。
同名但不同主键的记录会触发唯一约束错误，命令不会替你清表或猜测合并。

旧版本启动时生成过 `browser_staff`、`browser_superuser_guard` 等固定测试账号；
更新源码不会擅自删除它们。已有数据库请在 Admin 中自行检查并禁用或删除不再需要的测试账号，
不要将含固定测试密码的数据库对外开放。现在这些账号只在隔离的浏览器验证脚本中创建。

## 验证

```bash
.venv/bin/python -m unittest discover -s tests -t .
.venv/bin/python scripts/verify-notifications-browser-with-server.py --browser chrome
.venv/bin/python scripts/verify-notifications-browser-with-server.py --browser firefox
.venv/bin/python scripts/verify-admin-browser-with-servers.py
```

浏览器脚本会启动隔离的 Redis、数据库和服务，只清理自己创建的进程与临时文件。

## 框架文档

实际配置和操作对应 [Admin 用户教程](https://github.com/alexliyu7352/oldman/blob/master/docs/users/admin.md)；模型注册、权限、模板及共享前端扩展见 [Admin 开发者参考](https://github.com/alexliyu7352/oldman/blob/master/docs/developers/admin.md)与 [Agent 接线指南](https://github.com/alexliyu7352/oldman/blob/master/docs/agents/admin.md)。使用与本地框架/Demo 提交匹配的文档，不能把本地验证误称为远端已经发布。

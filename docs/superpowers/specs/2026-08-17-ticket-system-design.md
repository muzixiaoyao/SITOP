# SITOP 工单系统设计文档

> 日期：2026-08-17
> 状态：设计中（待审阅）
> 架构方案：方案 A — SITOP 内嵌模块

---

## 1. 背景与目标

### 1.1 业务背景

SITOP 当前是一个面向运维场景的服务器智能任务编排平台，服务于一家 ICT 解决方案和运维公司。该公司管理多个机房和客户服务器，需要一个综合工单系统来处理：

- **外部客户**（企业租户/个人用户）提交的故障报告和服务需求
- **内部团队**（研发/测试）提交的资源申请和运维请求

### 1.2 设计目标

- 在 SITOP 内新增 `apps/tickets` 模块，作为工单系统的核心
- 支持四种工单类型：故障工单、需求工单、内部请求、变更工单（可选关联 SITOP 任务）
- 可配置流程引擎：不同工单类型走不同流转规则
- 完整 SLA 管理：响应时限、处理时限、超时自动升级
- 站内通知 + 邮件通知
- 统一用户体系，通过角色区分权限和菜单可见性

### 1.3 架构决策

选择 **方案 A：SITOP 内嵌模块**，理由：

1. 工单是运维服务的延伸，不是独立产品，与 SITOP 定位一致
2. 复用现有基础设施：多租户、JWT 认证、角色权限、审计日志、Celery、WebSocket
3. 工单与 SITOP 任务天然关联（同一数据库，直接 FK）
4. 部署零额外成本，不增加运维复杂度
5. 留有退路：如果工单模块未来需要独立，Django app 拆分是成熟实践

---

## 2. 用户与角色体系

### 2.1 角色定义

在现有 `User.role` 字段中扩展角色：

| 角色 | 标识 | 归属 | 权限范围 |
|------|------|------|----------|
| 平台管理员 | `platform_admin` | ICT 公司 | 全部权限，管理所有租户，配置工单流程模板 |
| 运维员 | `operator` | ICT 公司 | 运维后台全功能（原 `admin` 角色，保持兼容） |
| 只读 | `viewer` | ICT 公司 | 运维后台只读 |
| 企业管理员 | `enterprise_admin` | 客户企业 | 工单全功能 + 查看本企业全部工单 |
| 企业员工 | `enterprise_user` | 客户企业 | 提工单、查自己的工单 |

### 2.2 数据模型变更

```python
# User.role 新增 choices
ROLE_CHOICES = [
    ("platform_admin", "平台管理员"),
    ("operator", "运维员"),
    ("viewer", "只读"),
    ("enterprise_admin", "企业管理员"),
    ("enterprise_user", "企业员工"),
]
```

### 2.3 设计要点

- **租户隔离不变** —— 每个客户企业仍是一个 `Tenant`，数据隔离逻辑不变
- **ICT 公司自身也是 Tenant** —— 平台管理员属于 ICT 公司的租户
- **`admin` 重命名为 `platform_admin`** —— 避免与 Django 内置 admin 混淆，migration 中处理向后兼容
- **菜单按角色动态渲染** —— 前端根据角色决定展示哪些菜单项，不做独立门户页面
- **企业员工数据范围** —— `enterprise_user` 只能看到自己提交的工单；`enterprise_admin` 能看到本企业所有工单

---

## 3. 工单数据模型

### 3.1 模型关系图

```
Ticket（工单）
├── tenant: FK → Tenant           所属租户
├── submitter: FK → User          提交人
├── assignee: FK → User           当前处理人
├── current_node: FK → TicketNode 当前流程节点
├── sla_policy: FK → SLAPolicy    适用 SLA 策略
├── related_job: FK → Job (null)  关联 SITOP 任务（仅变更工单）
│
├── TicketFlow（流转模板）
│   └── TicketNode（流程节点）×N
│
├── TicketTemplate（工单模板）    预填表单模板
├── TicketTransition（流转记录）×N
├── TicketComment（工单评论）×N
└── TicketAttachment（附件）×N

Article（知识库文章）
├── category: FK → ArticleCategory 分类
├── author: FK → User              作者
└── (独立模块，与工单松耦合)
```

### 3.2 Ticket 工单主表

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | UUIDField | 主键 |
| `tenant` | FK → Tenant | 所属租户 |
| `ticket_no` | CharField | 工单编号 `TK-{YYYYMMDD}-{4位序号}`，每日重置 |
| `title` | CharField(200) | 工单标题 |
| `description` | TextField | 问题描述（Markdown） |
| `type` | CharField(20) | `fault` / `request` / `internal` / `change` |
| `priority` | CharField(20) | `critical` / `high` / `medium` / `low` |
| `status` | CharField(20) | `pending` / `assigned` / `processing` / `resolved` / `closed` / `cancelled` |
| `current_node` | FK → TicketNode | 当前所处流程节点 |
| `submitter` | FK → User | 提交人 |
| `assignee` | FK → User (null) | 当前处理人 |
| `related_job` | FK → Job (null) | 关联的 SITOP 任务 |
| `sla_policy` | FK → SLAPolicy | 适用的 SLA 策略 |
| `custom_data` | JSONField (null) | 工单模板自定义字段数据 |
| `first_response_at` | DateTimeField (null) | 首次响应时间（响应 SLA 终点） |
| `assigned_at` | DateTimeField (null) | 首次分派时间（处理 SLA 起点） |
| `resolved_at` | DateTimeField (null) | 解决时间（处理 SLA 终点） |
| `closed_at` | DateTimeField (null) | 关闭时间 |
| `created_at` | DateTimeField | 创建时间 |
| `updated_at` | DateTimeField | 更新时间 |

**索引**：`ticket_no`（唯一）、`tenant + status`、`tenant + created_at`、`assignee + status`

### 3.3 TicketFlow 流转模板

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | UUIDField | 主键 |
| `tenant` | FK → Tenant (null) | 所属租户（null 表示全局模板） |
| `name` | CharField(100) | 模板名称 |
| `ticket_type` | CharField(20) | 适用工单类型 |
| `is_active` | BooleanField | 是否启用 |
| `created_at` | DateTimeField | 创建时间 |

### 3.4 TicketNode 流程节点

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | UUIDField | 主键 |
| `flow` | FK → TicketFlow | 所属流程模板 |
| `name` | CharField(100) | 节点名称 |
| `order` | IntegerField | 节点顺序 |
| `role_required` | CharField(20) | 处理此节点所需角色 |
| `is_terminal` | BooleanField | 是否终止节点 |
| `sla_hours` | IntegerField | 此节点处理时限（小时） |
| `auto_assign_rule` | CharField(20) | `round_robin` / `least_load` / `manual` |

### 3.5 SLAPolicy SLA 策略

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | UUIDField | 主键 |
| `name` | CharField(100) | 策略名称 |
| `priority` | CharField(20) | 适用优先级 |
| `response_minutes` | IntegerField | 响应时限（分钟） |
| `resolve_minutes` | IntegerField | 处理时限（分钟） |
| `escalation_rules` | JSONField | 超时升级规则 |

**escalation_rules 示例：**

```json
{
  "response_timeout": [
    {"minutes": 30, "action": "notify_assignee"},
    {"minutes": 60, "action": "notify_manager"},
    {"minutes": 120, "action": "escalate_to_l3"}
  ],
  "resolve_timeout": [
    {"percent": 80, "action": "warning"},
    {"percent": 100, "action": "escalate_to_manager"}
  ]
}
```

### 3.6 TicketTransition 流转记录

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | UUIDField | 主键 |
| `ticket` | FK → Ticket | 所属工单 |
| `from_node` | FK → TicketNode (null) | 来源节点 |
| `to_node` | FK → TicketNode | 目标节点 |
| `operator` | FK → User | 操作人 |
| `comment` | TextField (blank) | 操作备注 |
| `duration_seconds` | IntegerField | 在源节点停留时长 |
| `created_at` | DateTimeField | 操作时间 |

### 3.7 TicketComment 工单评论

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | UUIDField | 主键 |
| `ticket` | FK → Ticket | 所属工单 |
| `author` | FK → User | 评论人 |
| `content` | TextField | 评论内容（Markdown） |
| `is_system` | BooleanField | 是否系统自动评论 |
| `created_at` | DateTimeField | 创建时间 |

### 3.8 TicketAttachment 附件

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | UUIDField | 主键 |
| `ticket` | FK → Ticket | 所属工单 |
| `file` | FileField | 文件 |
| `filename` | CharField | 原始文件名 |
| `size` | IntegerField | 文件大小（字节） |
| `uploaded_by` | FK → User | 上传人 |
| `created_at` | DateTimeField | 上传时间 |

### 3.9 Notification 通知

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | UUIDField | 主键 |
| `user` | FK → User | 接收人 |
| `type` | CharField(30) | 通知类型 |
| `title` | CharField(200) | 通知标题 |
| `content` | TextField | 通知内容 |
| `ticket` | FK → Ticket (null) | 关联工单 |
| `is_read` | BooleanField | 是否已读 |
| `created_at` | DateTimeField | 创建时间 |

**索引**：`user + is_read + created_at`

---

## 4. 流程引擎

### 4.1 核心思路

基于有限状态机（FSM），工单创建时绑定一个 `TicketFlow`，状态变更只能沿模板定义的节点顺序进行。

### 4.2 状态流转

```
pending ──▶ assigned ──▶ processing ──▶ resolved ──▶ closed
 (待受理)    (已分派)     (处理中)       (已解决)    (已关闭)
                │            │
                │            └──▶ 升级节点（可选）──▶ processing
                │
                └──▶ cancelled（任意非终态均可取消）
```

### 4.3 TicketEngine 核心方法

```python
class TicketEngine:
    def create_ticket(self, data, submitter) -> Ticket:
        """创建工单，绑定流程模板，初始化 SLA"""
        # 1. 根据 ticket_type 查找匹配的 active TicketFlow
        # 2. 创建 Ticket，status=pending，current_node=第一个节点
        # 3. 启动 SLA 计时（记录 created_at）
        # 4. 触发自动分派（如果第一个节点有 auto_assign_rule）
        # 5. 发送通知给 submitter

    def assign(self, ticket, assignee, operator) -> None:
        """分派工单到指定处理人"""
        # 1. 验证 operator 有权限操作当前节点
        # 2. 更新 ticket.assignee，状态变为 assigned
        # 3. 记录 TicketTransition
        # 4. 通知 assignee

    def transition(self, ticket, target_node, operator, comment=None) -> None:
        """流转到下一个节点"""
        # 1. 验证 target_node 是当前节点的合法后继
        # 2. 验证 operator 角色满足 role_required
        # 3. 更新 current_node, status
        # 4. 记录 TicketTransition（含耗时）
        # 5. 重置节点级 SLA 计时
        # 6. 通知相关人

    def resolve(self, ticket, operator, resolution) -> None:
        """解决工单"""
        # 1. 流转到 resolved 状态
        # 2. 记录 resolved_at
        # 3. 通知 submitter 确认

    def close(self, ticket, operator_or_submitter) -> None:
        """关闭工单"""

    def cancel(self, ticket, operator_or_submitter, reason) -> None:
        """取消工单"""

    def escalate(self, ticket) -> None:
        """SLA 超时升级"""
        # 1. 根据 escalation_rules 执行升级
        # 2. 通知更高级别处理人
        # 3. 可选：自动转派
```

### 4.4 自动分派策略

| 策略 | 说明 |
|------|------|
| `manual` | 不自动分派，由当前节点角色的处理人手动认领 |
| `round_robin` | 轮询分派给该角色的所有用户 |
| `least_load` | 分派给当前处理中工单数最少的用户 |

### 4.5 设计要点

- **流程模板可配置** —— `platform_admin` 可以为每种工单类型创建/编辑流程模板
- **节点级 SLA** —— 每个节点可以有自己的处理时限
- **流转不可逆** —— 工单只能向前流转，不能回退（如需"退回"，设计为特殊反向节点）
- **取消全局允许** —— 任何非终态工单可被 submitter 或 `platform_admin` 取消
- **流转记录不可变** —— TicketTransition 只追加，不修改不删除

---

## 5. SLA 管理

### 5.1 计时机制

工单创建时，根据 `priority` 匹配 `SLAPolicy`，启动两个计时器：

| 计时器 | 起点 | 终点 | 说明 |
|--------|------|------|------|
| 响应计时 | `created_at` | `first_response_at` | 客户等待首次响应的时间 |
| 处理计时 | `assigned_at` | `resolved_at` | 实际处理耗时（不含排队等待分派的时间） |

### 5.2 超时升级流程

```
工单创建 → 响应 SLA 计时开始
    │
    ├── 响应时限 50%  → 站内预警（黄色）
    ├── 响应时限 80%  → 站内预警（橙色）+ 通知处理人
    ├── 响应时限 100% → SLA 违规（红色）+ 通知管理者 + 自动升级
    │
工单分派 → 处理 SLA 计时开始（assigned_at）
    │
    ├── 处理时限 80%  → 站内预警
    └── 处理时限 100% → SLA 违规 + 升级至更高级别
```

### 5.3 实现方式

- **Celery Beat 定时任务**：每 5 分钟扫描未关闭工单，检查 SLA 状态
- **SLA 暂停**：工单 `resolved` 状态（等待客户确认）时，处理计时暂停
- **SLA 冻结**：工单 `cancelled` 后，所有计时器停止

### 5.4 SLA 统计

仪表盘增加工单 SLA 统计卡片：
- 平均响应时间
- 平均处理时间
- SLA 达标率
- 各优先级工单分布

---

## 6. 通知系统

### 6.1 通知渠道

| 渠道 | 实现 | 说明 |
|------|------|------|
| 站内通知 | `Notification` 模型 | 前端顶栏铃铛图标 + 下拉列表 |
| 邮件通知 | Celery 异步任务 + Django EmailBackend | 关键事件触发 |

### 6.2 通知事件矩阵

| 事件 | 通知对象 | 站内 | 邮件 |
|------|----------|------|------|
| 工单创建 | 提交人 | ✅ | ✅ |
| 工单分派 | 被分派人 | ✅ | ✅ |
| 工单流转 | 下一节点处理人 | ✅ | ✅ |
| 工单解决 | 提交人 | ✅ | ✅ |
| 工单关闭 | 提交人 + 处理人 | ✅ | ❌ |
| SLA 预警 | 处理人 + 管理者 | ✅ | ✅ |
| SLA 违规 | 管理者 | ✅ | ✅ |
| 工单评论 | 相关人 | ✅ | ❌ |

### 6.3 前端通知交互

- 顶栏右侧铃铛图标，显示未读数角标
- 点击展开通知列表（最近 20 条）
- 点击通知跳转到对应工单详情页
- "全部已读"按钮
- 站内通知 TTL：90 天自动清理

---

## 7. SITOP 任务关联

### 7.1 关联方式

- **数据库层**：`Ticket.related_job` FK 指向 `apps.tasks.Job`
- **事件层**：工单状态变更时通过 Django signal 触发 Job 相关操作
- **权限层**：只有 `platform_admin` 和 `operator` 可关联 SITOP 任务

### 7.2 集成行为

- 变更工单可选择性关联 SITOP 任务（`related_job` 为 nullable）
- 工单详情页中，如有 `related_job`，显示 SITOP 任务卡片（名称、状态、进度）
- 点击卡片跳转到 `/jobs/{id}` 任务详情页
- 客户角色（`enterprise_*`）看不到 SITOP 相关内容

---

## 8. 前端设计

### 8.1 新增路由

| 路由 | 页面 | 可见角色 |
|------|------|----------|
| `/tickets` | 工单列表页 | 所有角色 |
| `/tickets/create` | 创建工单 | 所有角色 |
| `/tickets/:id` | 工单详情页 | 所有角色（数据按权限过滤） |
| `/tickets/flows` | 流程模板管理 | `platform_admin` |
| `/tickets/sla` | SLA 策略管理 | `platform_admin` |
| `/tickets/templates` | 工单模板管理 | `platform_admin` |
| `/kb` | 知识库首页 | 所有角色 |
| `/kb/search` | 搜索结果页 | 所有角色 |
| `/kb/:slug` | 文章详情页 | 所有角色 |
| `/kb/admin` | 文章管理 | `platform_admin` |

### 8.2 侧边栏菜单

```
仪表盘
服务器管理          ← ICT 角色可见
脚本库              ← ICT 角色可见
模板编排            ← ICT 角色可见
任务中心            ← ICT 角色可见
软件仓库            ← ICT 角色可见
───────────
工单管理            ← 所有角色可见
  ├ 我的工单
  ├ 全部工单        ← ICT 角色 + enterprise_admin 可见
  ├ 流程模板        ← platform_admin 可见
  ├ SLA 策略        ← platform_admin 可见
  └ 工单模板        ← platform_admin 可见
───────────
知识库              ← 所有角色可见
───────────
审计日志            ← ICT 角色可见
用户管理            ← platform_admin 可见
```

### 8.3 工单列表页

- 顶部筛选栏：工单类型、优先级、状态、日期范围、关键词搜索
- 表格列：工单编号、标题、类型、优先级（彩色标签）、状态、提交人、处理人、创建时间、SLA 状态
- SLA 状态列：绿色（正常）/ 黄色（预警）/ 红色（违规）/ 灰色（已暂停）
- 批量操作：批量分派、批量关闭
- 数据范围按角色自动过滤

### 8.4 工单详情页布局

```
┌──────────────────────────────────────────────────┐
│ TK-20260817-0001  [故障] [紧急] [处理中]          │
│ 标题：生产数据库连接超时                            │
├──────────────────────────────────────────────────┤
│ 描述（Markdown 渲染）                              │
│ 附件列表                                           │
├──────────────────────────────────────────────────┤
│ 流程进度条：                                       │
│ [待受理] → [已分派] → [●处理中] → [已解决] → [已关闭] │
├──────────────────────────────────────────────────┤
│ SLA 状态：                                         │
│ 响应：✅ 15分钟（时限30分钟）                        │
│ 处理：⏳ 已用2小时/时限4小时 [████████░░] 50%        │
├──────────────────────────────────────────────────┤
│ 关联 SITOP 任务：[Job #1234 - 数据库集群初始化]      │
├──────────────────────────────────────────────────┤
│ 操作区：                                           │
│ [分派给...] [流转到下一节点] [解决] [取消]            │
├──────────────────────────────────────────────────┤
│ 沟通记录（时间线）：                                 │
│ ┌ 张三 (一线) · 2小时前 ─────────────────┐          │
│ │ 已接单，正在排查数据库连接池配置           │          │
│ └──────────────────────────────────────┘          │
│ ┌ 系统 · 1小时前 ────────────────────────┐          │
│ │ 工单从"已分派"流转到"处理中"              │          │
│ └──────────────────────────────────────┘          │
│ [输入评论...] [发送]                                │
└──────────────────────────────────────────────────┘
```

---

## 9. API 设计

### 9.1 工单 CRUD

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/api/tickets/` | 工单列表（按权限过滤） |
| `POST` | `/api/tickets/` | 创建工单 |
| `GET` | `/api/tickets/{id}/` | 工单详情 |

### 9.2 工单操作

| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/api/tickets/{id}/assign/` | 分派工单 |
| `POST` | `/api/tickets/{id}/transition/` | 流转工单 |
| `POST` | `/api/tickets/{id}/resolve/` | 解决工单 |
| `POST` | `/api/tickets/{id}/close/` | 关闭工单 |
| `POST` | `/api/tickets/{id}/cancel/` | 取消工单 |
| `POST` | `/api/tickets/{id}/comments/` | 添加评论 |
| `GET` | `/api/tickets/{id}/transitions/` | 流转记录 |

### 9.3 管理接口

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/api/tickets/flows/` | 流程模板列表 |
| `POST` | `/api/tickets/flows/` | 创建流程模板 |
| `PUT` | `/api/tickets/flows/{id}/` | 编辑流程模板 |
| `GET` | `/api/tickets/sla-policies/` | SLA 策略列表 |
| `POST` | `/api/tickets/sla-policies/` | 创建 SLA 策略 |
| `GET` | `/api/tickets/templates/` | 工单模板列表 |
| `POST` | `/api/tickets/templates/` | 创建工单模板 |
| `PUT` | `/api/tickets/templates/{id}/` | 编辑工单模板 |
| `DELETE` | `/api/tickets/templates/{id}/` | 删除工单模板 |

### 9.4 导入导出

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/api/tickets/export/` | 导出工单（CSV） |
| `POST` | `/api/tickets/import/` | 导入工单（CSV 上传 + 预览） |
| `POST` | `/api/tickets/import/confirm/` | 确认导入 |

### 9.5 知识库

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/api/kb/articles/` | 文章列表（已发布） |
| `GET` | `/api/kb/articles/{slug}/` | 文章详情 |
| `GET` | `/api/kb/articles/search/?q=` | 搜索 |
| `GET` | `/api/kb/categories/` | 分类列表 |
| `POST` | `/api/kb/articles/` | 创建文章（仅 admin） |
| `PUT` | `/api/kb/articles/{id}/` | 编辑文章 |
| `DELETE` | `/api/kb/articles/{id}/` | 删除文章 |
| `POST` | `/api/kb/categories/` | 创建分类 |

### 9.6 通知接口

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/api/notifications/` | 通知列表 |
| `POST` | `/api/notifications/{id}/read/` | 标记已读 |
| `POST` | `/api/notifications/read-all/` | 全部已读 |
| `GET` | `/api/notifications/unread-count/` | 未读数量 |

---

## 10. 技术实现要点

### 10.1 后端

- **工单编号生成**：使用 Redis INCR 原子递增，格式 `TK-{YYYYMMDD}-{4位序号}`，每日 00:00 重置
- **SLA 扫描**：Celery Beat 每 5 分钟执行 `check_sla_timeouts` 任务
- **邮件发送**：Celery 异步任务，不阻塞主流程
- **权限过滤**：在 ViewSet 的 `get_queryset()` 中按用户角色和租户过滤
- **工单模块注册**：`apps/tickets/` 作为新 Django app，注册到 `INSTALLED_APPS`

### 10.2 前端

- **菜单动态渲染**：根据 `auth.user.role` 控制菜单项可见性
- **数据过滤**：API 层自动过滤，前端无需额外处理
- **工单详情时间线**：沟通记录 + 流转记录混合展示，按时间排序
- **SLA 进度条**：前端根据 `created_at`、SLA 时限和当前时间计算百分比
- **通知铃铛**：全局组件，定时轮询 `/api/notifications/unread-count/`

### 10.3 数据库迁移

- `User.role` 的 choices 变更需要 migration
- 原 `admin` 角色数据迁移为 `platform_admin`（或保持 `admin` 作为别名）
- 新增 8 个模型（Ticket, TicketFlow, TicketNode, SLAPolicy, TicketTransition, TicketComment, TicketAttachment, Notification）

---

## 11. 工单导入导出

### 11.1 导出

- **格式**：CSV（UTF-8 with BOM，兼容 Excel 中文）
- **范围**：支持按当前筛选条件导出（类型、优先级、状态、日期范围）
- **字段**：工单编号、标题、类型、优先级、状态、提交人、处理人、创建时间、解决时间、关闭时间
- **权限**：`platform_admin` / `operator` / `enterprise_admin` 可导出，`enterprise_user` 只能导出自己的工单
- **入口**：工单列表页顶部“导出”按钮

### 11.2 导入

- **格式**：CSV（UTF-8/GBK 自适应，复用现有服务器导入的解码策略）
- **必填字段**：标题、类型、优先级
- **可选字段**：描述、提交人（按用户名匹配）
- **导入后状态**：所有导入工单初始状态为 `pending`
- **权限**：仅 `platform_admin` / `operator` 可导入
- **入口**：工单列表页“导入”按钮，上传 CSV 后预览确认再提交

---

## 12. 工单模板（预设表单）

### 12.1 概念

工单模板 ≠ 流程模板（TicketFlow）。工单模板是**预填表单**，让客户快速提交标准化信息。

### 12.2 TicketTemplate 模型

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | UUIDField | 主键 |
| `name` | CharField(100) | 模板名称，如“服务器故障报告” |
| `description` | TextField | 模板说明 |
| `ticket_type` | CharField(20) | 对应工单类型 |
| `fields` | JSONField | 自定义字段定义 |
| `is_active` | BooleanField | 是否启用 |
| `order` | IntegerField | 排序 |
| `created_at` | DateTimeField | 创建时间 |

### 12.3 fields 示例

```json
{
  "custom_fields": [
    {"name": "server_ip", "label": "故障服务器IP", "type": "text", "required": true},
    {"name": "error_msg", "label": "错误信息", "type": "textarea", "required": false},
    {"name": "impact_level", "label": "影响范围", "type": "select", "options": ["单机", "部分服务", "全部服务"], "required": true}
  ]
}
```

### 12.4 前端交互

- 创建工单时，先选择工单模板（或“自由工单”）
- 选择模板后，表单动态渲染自定义字段
- 提交时，自定义字段值存入 `Ticket.description`（格式化为 Markdown）或新增 `Ticket.custom_data` JSONField

### 12.5 设计要点

- 工单模板由 `platform_admin` 管理
- 客户侧只看到启用的模板列表
- 不选模板也可以直接提交自由格式工单

---

## 13. 知识库 / FAQ

### 13.1 概念

供客户和企业用户自助查阅的常见问题和运维知识文章，减少重复工单。

### 13.2 Article 模型

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | UUIDField | 主键 |
| `title` | CharField(200) | 文章标题 |
| `slug` | SlugField | URL 友好标识，如 `reset-password` |
| `content` | TextField | 文章内容（Markdown） |
| `category` | FK → ArticleCategory | 分类 |
| `tags` | CharField(500) | 标签，逗号分隔 |
| `is_published` | BooleanField | 是否发布 |
| `view_count` | PositiveIntegerField | 浏览次数 |
| `author` | FK → User | 作者 |
| `created_at` | DateTimeField | 创建时间 |
| `updated_at` | DateTimeField | 更新时间 |

### 13.3 ArticleCategory 模型

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | UUIDField | 主键 |
| `name` | CharField(50) | 分类名称，如“账号管理”、“常见故障” |
| `order` | IntegerField | 排序 |

### 13.4 前端页面

| 路由 | 页面 | 可见角色 |
|------|------|----------|
| `/kb` | 知识库首页（分类列表 + 热门文章） | 所有角色 |
| `/kb/search?q=` | 搜索结果页 | 所有角色 |
| `/kb/:slug` | 文章详情页 | 所有角色 |
| `/kb/admin` | 文章管理（CRUD） | `platform_admin` |

### 13.5 API

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/api/kb/articles/` | 文章列表（已发布） |
| `GET` | `/api/kb/articles/{slug}/` | 文章详情 |
| `GET` | `/api/kb/articles/search/?q=` | 搜索（标题 + 内容全文匹配） |
| `GET` | `/api/kb/categories/` | 分类列表 |
| `POST` | `/api/kb/articles/` | 创建文章（仅 `platform_admin`） |
| `PUT` | `/api/kb/articles/{id}/` | 编辑文章 |
| `DELETE` | `/api/kb/articles/{id}/` | 删除文章 |

### 13.6 设计要点

- 搜索使用 PostgreSQL `__icontains` 或 `__search`（全文检索）
- 工单创建页可展示“相关文章”推荐（按工单类型匹配分类）
- 知识库对 `enterprise_user` 也可见（鼓励自助解决）

---

## 14. 不做的事情（YAGNI）

- ❌ 独立门户页面（`/portal`）—— 不做，统一界面按角色渲染菜单
- ❌ 子账号管理 —— 不做，企业管理员不能管理子账号
- ❌ 用户自定义通知偏好 —— 不做，先使用固定通知规则
- ❌ 客户满意度评价 —— 不做，后续迭代
- ❌ 工单合并/拆分 —— 不做

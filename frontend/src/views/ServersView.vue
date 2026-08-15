<template>
  <AppLayout>
    <div class="servers-page">
      <el-card class="group-panel">
        <template #header>
          <div class="panel-header">
            <span>服务器分组</span>
            <el-button type="primary" size="small" @click="openCreateGroup">新建分组</el-button>
          </div>
        </template>
        <el-input
          v-model="groupSearch" clearable size="small" placeholder="搜索分组"
          style="margin-bottom: 8px"
        >
          <template #prefix><el-icon><search /></el-icon></template>
        </el-input>
        <el-menu :default-active="selectedGroupId" @select="selectGroup">
          <el-menu-item index="__all__">
            <div class="group-item">
              <span class="group-name">全部服务器</span>
              <el-badge :value="totalServerCount" :max="999" />
            </div>
          </el-menu-item>
          <el-menu-item v-for="group in filteredGroups" :key="group.id" :index="group.id">
            <div class="group-item">
              <span class="group-name">{{ group.name }}</span>
              <el-badge :value="group.server_count" :max="99" />
              <el-dropdown trigger="click" @command="(cmd: string) => handleGroupCommand(cmd, group)" @click.stop>
                <el-icon class="group-action" title="更多操作" @click.stop><more-filled /></el-icon>
                <template #dropdown>
                  <el-dropdown-menu>
                    <el-dropdown-item command="detail">分组详情</el-dropdown-item>
                    <el-dropdown-item command="edit">编辑分组</el-dropdown-item>
                    <el-dropdown-item command="delete" divided>删除分组</el-dropdown-item>
                  </el-dropdown-menu>
                </template>
              </el-dropdown>
            </div>
          </el-menu-item>
        </el-menu>
        <el-empty v-if="groups.length === 0" description="暂无分组" />
        <el-empty v-else-if="filteredGroups.length === 0" description="未找到匹配的分组" :image-size="60" />
      </el-card>

      <el-card class="server-panel" v-if="selectedGroup">
        <template #header>
          <div class="panel-header">
            <span>{{ selectedGroup.name }} - 服务器列表</span>
            <div class="header-actions">
              <el-input
                v-model="serverSearch" clearable size="small"
                placeholder="搜索主机名 / IP / 标签"
                style="width: 260px"
              >
                <template #prefix><el-icon><search /></el-icon></template>
                <template #append>
                  <el-select v-model="searchMode" style="width: 88px">
                    <el-option value="fuzzy" label="模糊" />
                    <el-option value="exact" label="精确" />
                  </el-select>
                </template>
              </el-input>
              <el-dropdown @command="handleBatchCommand" :disabled="selectedIds.size === 0">
                <el-button type="primary" size="small" :disabled="selectedIds.size === 0">
                  批量操作 ({{ selectedIds.size }})
                  <el-icon class="el-icon--right"><arrow-down /></el-icon>
                </el-button>
                <template #dropdown>
                  <el-dropdown-menu>
                    <el-dropdown-item command="connectivity">批量连通性测试</el-dropdown-item>
                    <el-dropdown-item command="credential">批量更新凭据</el-dropdown-item>
                    <el-dropdown-item command="group-move" divided>移动分组</el-dropdown-item>
                    <el-dropdown-item command="group-add">增加分组</el-dropdown-item>
                    <el-dropdown-item command="delete" divided>批量删除</el-dropdown-item>
                  </el-dropdown-menu>
                </template>
              </el-dropdown>
              <el-button v-if="!isGlobalView" type="success" size="small" :loading="connectivityLoading" @click="checkConnectivity">测试连通性</el-button>
              <el-button v-if="!isGlobalView" type="warning" size="small" @click="showCommandDialog = true">执行命令</el-button>
              <el-button v-if="!isGlobalView" size="small" @click="showImportDialog = true">导入</el-button>
              <el-button v-if="!isGlobalView" size="small" @click="exportServers">导出</el-button>
              <el-button v-if="!isGlobalView" size="small" @click="showAddServer = true">添加服务器</el-button>
            </div>
          </div>
        </template>
        <el-table
          ref="tableRef"
          :data="pagedServers" row-key="id" stripe v-loading="serversLoading"
          @selection-change="handleSelectionChange"
          @filter-change="handleFilterChange"
          @row-click="showServerDetail"
          style="cursor: pointer"
          max-height="calc(100vh - 200px)"
        >
          <el-table-column type="selection" width="55">
            <template #header>
              <el-checkbox
                :model-value="isAllSelected"
                :indeterminate="isPartialSelected"
                @change="toggleSelectAll"
              />
            </template>
          </el-table-column>
          <el-table-column prop="hostname" label="主机名" width="160" />
          <el-table-column prop="ip" label="IP 地址" width="140" />
          <el-table-column prop="ssh_port" label="端口" width="80" column-key="ssh_port" :filters="portFilters" :filter-method="() => true" />
          <el-table-column prop="protocol" label="协议" width="90" column-key="protocol" :filters="protocolFilters" :filter-method="() => true">
            <template #default="{ row }">
              <el-tag size="small">{{ row.protocol?.toUpperCase() || 'SSH' }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="platform" label="平台" width="110" column-key="platform" :filters="platformFilters" :filter-method="() => true">
            <template #default="{ row }">
              <span>{{ platformLabel(row.platform) }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="connectivity_status" label="连通性" width="110" column-key="connectivity_status" :filters="connectivityFilters" :filter-method="() => true">
            <template #default="{ row }">
              <el-tag :type="statusType(row.connectivity_status)" size="small">{{ statusLabel(row.connectivity_status) }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="分组" min-width="180" column-key="groups" :filters="groupFilters" :filter-method="() => true">
            <template #default="{ row }">
              <el-tag
                v-for="g in (row.groups || [])" :key="g.id"
                size="small" type="info" style="margin-right: 4px; margin-bottom: 2px"
              >{{ g.name }}</el-tag>
              <span v-if="!row.groups || row.groups.length === 0" style="color: #999">未分组</span>
            </template>
          </el-table-column>
          <el-table-column prop="tags" label="标签" width="150" column-key="tags" :filters="tagFilters" :filter-method="() => true">
            <template #default="{ row }">
              <el-tag v-for="tag in (row.tags || [])" :key="tag" size="small" style="margin-right: 4px">{{ tag }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="120">
            <template #default="{ row }">
              <el-button type="primary" size="small" link @click.stop="editServer(row)">编辑</el-button>
              <el-button type="danger" size="small" link @click.stop="deleteServer(row.id)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>
        <div style="display: flex; justify-content: space-between; align-items: center; margin-top: 12px">
          <div style="display: flex; align-items: center; gap: 8px">
            <span style="font-size: 13px; color: #909399">每页</span>
            <el-select v-model="pageSize" style="width: 110px" @change="handlePageSizeChange">
              <el-option :value="20" label="20 条" />
              <el-option :value="50" label="50 条" />
              <el-option :value="100" label="100 条" />
              <el-option :value="200" label="200 条" />
              <el-option :value="0" label="全部" />
            </el-select>
          </div>
          <el-pagination
            v-if="pageSize > 0"
            :current-page="currentPage"
            :page-size="pageSize"
            :total="filteredServers.length"
            layout="total, prev, pager, next"
            @current-change="handlePageChange"
          />
          <span v-else style="font-size: 13px; color: #909399">共 {{ filteredServers.length }} 台</span>
        </div>
      </el-card>
      <el-card v-else class="server-panel"><el-empty description="请选择一个分组" /></el-card>

      <!-- Server Detail Drawer -->
      <el-drawer v-model="showDetailDrawer" :title="detailServer?.hostname || '服务器详情'" size="480px">
        <template v-if="detailServer">
          <el-descriptions :column="2" border>
            <el-descriptions-item label="主机名">{{ detailServer.hostname }}</el-descriptions-item>
            <el-descriptions-item label="IP 地址">{{ detailServer.ip }}</el-descriptions-item>
            <el-descriptions-item label="端口">{{ detailServer.ssh_port }}</el-descriptions-item>
            <el-descriptions-item label="协议">
              <el-tag size="small">{{ detailServer.protocol?.toUpperCase() || 'SSH' }}</el-tag>
            </el-descriptions-item>
            <el-descriptions-item label="平台">{{ platformLabel(detailServer.platform) }}</el-descriptions-item>
            <el-descriptions-item label="系统信息">{{ detailServer.os_info || '-' }}</el-descriptions-item>
            <el-descriptions-item label="连通性">
              <el-tag :type="statusType(detailServer.connectivity_status)" size="small">{{ statusLabel(detailServer.connectivity_status) }}</el-tag>
            </el-descriptions-item>
            <el-descriptions-item label="最后检测">{{ detailServer.last_check_time || '从未' }}</el-descriptions-item>
            <el-descriptions-item label="连接超时">{{ detailServer.connect_timeout }}s</el-descriptions-item>
            <el-descriptions-item label="执行超时">{{ detailServer.exec_timeout }}s</el-descriptions-item>
            <el-descriptions-item label="SSH 凭据">{{ credentialName(detailServer.ssh_credential) }}</el-descriptions-item>
          </el-descriptions>

          <h4 style="margin: 16px 0 8px">所属分组</h4>
          <div class="detail-groups">
            <el-tag
              v-for="g in (detailServer.groups || [])" :key="g.id"
              size="default" type="info" style="margin: 0 6px 6px 0"
            >{{ g.name }}</el-tag>
            <span v-if="!detailServer.groups || detailServer.groups.length === 0" style="color: #999">未分组</span>
          </div>

          <h4 style="margin: 16px 0 8px" v-if="detailServer.tags?.length">标签</h4>
          <div>
            <el-tag v-for="tag in (detailServer.tags || [])" :key="tag" size="default" style="margin: 0 6px 6px 0">{{ tag }}</el-tag>
          </div>

          <h4 style="margin: 16px 0 8px" v-if="detailServer.comment">备注</h4>
          <p v-if="detailServer.comment" style="color: #606266; white-space: pre-wrap">{{ detailServer.comment }}</p>
        </template>
      </el-drawer>

      <!-- Create/Edit Group Dialog -->
      <el-dialog v-model="showCreateGroup" :title="editingGroupId ? '编辑分组' : '新建分组'" width="460px" @close="closeGroupDialog">
        <el-form :model="groupForm" label-width="100px">
          <el-form-item label="分组名称" required><el-input v-model="groupForm.name" /></el-form-item>
          <el-form-item label="描述"><el-input v-model="groupForm.description" type="textarea" /></el-form-item>
          <el-form-item label="默认凭据">
            <el-select v-model="groupForm.default_credential" clearable filterable placeholder="该分组服务器的默认SSH凭据" style="width: 100%">
              <el-option v-for="c in credentials" :key="c.id" :label="`${c.name} (${c.username})`" :value="c.id" />
            </el-select>
          </el-form-item>
          <el-form-item label="自动巡检">
            <el-switch v-model="groupForm.auto_patrol" />
          </el-form-item>
        </el-form>
        <template #footer>
          <el-button @click="closeGroupDialog">取消</el-button>
          <el-button type="primary" :loading="creating" @click="saveGroup">{{ editingGroupId ? '保存' : '创建' }}</el-button>
        </template>
      </el-dialog>

      <!-- Group Detail Drawer -->
      <el-drawer v-model="showGroupDetailDrawer" :title="detailGroup?.name || '分组详情'" size="520px">
        <template v-if="detailGroup">
          <el-descriptions :column="1" border>
            <el-descriptions-item label="描述">{{ detailGroup.description || '-' }}</el-descriptions-item>
            <el-descriptions-item label="默认凭据">{{ credentialName(detailGroup.default_credential) }}</el-descriptions-item>
            <el-descriptions-item label="自动巡检">{{ detailGroup.auto_patrol ? '开启' : '关闭' }}</el-descriptions-item>
            <el-descriptions-item label="服务器数量">{{ detailGroup.server_count }}</el-descriptions-item>
          </el-descriptions>
          <h4 style="margin: 16px 0 8px">成员服务器</h4>
          <el-table empty-text="暂无数据" :data="detailGroup.servers || []" size="small" max-height="400">
            <el-table-column prop="hostname" label="主机名" />
            <el-table-column prop="ip" label="IP" width="130" />
            <el-table-column prop="ssh_port" label="端口" width="70" />
            <el-table-column label="连通性" width="90">
              <template #default="{ row }">
                <el-tag :type="statusType(row.connectivity_status)" size="small">{{ statusLabel(row.connectivity_status) }}</el-tag>
              </template>
            </el-table-column>
          </el-table>
        </template>
      </el-drawer>

      <!-- Add/Edit Server Dialog -->
      <el-dialog v-model="showAddServer" :title="editingServerId ? '编辑服务器' : '添加服务器'" width="700px">
        <el-form :model="serverForm" label-width="100px">
          <el-row :gutter="16">
            <el-col :span="12">
              <el-form-item label="主机名" required><el-input v-model="serverForm.hostname" /></el-form-item>
            </el-col>
            <el-col :span="12">
              <el-form-item label="IP 地址" required><el-input v-model="serverForm.ip" /></el-form-item>
            </el-col>
          </el-row>
          <el-row :gutter="16">
            <el-col :span="8">
              <el-form-item label="端口"><el-input-number v-model="serverForm.ssh_port" :min="1" :max="65535" style="width: 100%" /></el-form-item>
            </el-col>
            <el-col :span="8">
              <el-form-item label="协议">
                <el-select v-model="serverForm.protocol" style="width: 100%">
                  <el-option label="SSH" value="ssh" />
                  <el-option label="RDP" value="rdp" />
                  <el-option label="Telnet" value="telnet" />
                  <el-option label="VNC" value="vnc" />
                </el-select>
              </el-form-item>
            </el-col>
            <el-col :span="8">
              <el-form-item label="平台">
                <el-select v-model="serverForm.platform" style="width: 100%">
                  <el-option label="Linux" value="linux" />
                  <el-option label="Windows" value="windows" />
                  <el-option label="Unix" value="unix" />
                  <el-option label="网络设备" value="network" />
                  <el-option label="其他" value="other" />
                </el-select>
              </el-form-item>
            </el-col>
          </el-row>
          <el-row :gutter="16">
            <el-col :span="12">
              <el-form-item label="连接超时(秒)"><el-input-number v-model="serverForm.connect_timeout" :min="1" :max="300" style="width: 100%" /></el-form-item>
            </el-col>
            <el-col :span="12">
              <el-form-item label="执行超时(秒)"><el-input-number v-model="serverForm.exec_timeout" :min="10" :max="3600" style="width: 100%" /></el-form-item>
            </el-col>
          </el-row>
          <el-form-item label="认证方式">
            <el-radio-group v-model="serverForm.auth_type" style="width: 100%">
              <el-radio value="credential">使用凭据</el-radio>
              <el-radio value="password">密码</el-radio>
              <el-radio value="key">私钥</el-radio>
            </el-radio-group>
          </el-form-item>

          <!-- 已有凭据 -->
          <el-form-item label="SSH 凭据" v-if="serverForm.auth_type === 'credential'">
            <div style="display: flex; gap: 8px; width: 100%">
              <el-select v-model="serverForm.ssh_credential" clearable filterable placeholder="选择凭据（留空则用分组默认凭据）" style="flex: 1">
                <el-option v-for="c in credentials" :key="c.id" :label="`${c.name} (${c.username}@${authTypeLabel(c.auth_type)})`" :value="c.id" />
              </el-select>
              <el-button type="primary" plain @click="openCredentialDialog()">新建凭据</el-button>
              <el-button v-if="serverForm.ssh_credential" type="warning" plain @click="openCredentialDialog(credentials.find(c => c.id === serverForm.ssh_credential))">编辑</el-button>
            </div>
          </el-form-item>

          <!-- 内联密码 -->
          <template v-if="serverForm.auth_type === 'password'">
            <el-form-item label="用户名" required>
              <el-input v-model="serverForm.auth_username" placeholder="SSH 登录用户名" />
            </el-form-item>
            <el-form-item label="密码" required>
              <el-input v-model="serverForm.auth_password" type="password" show-password placeholder="SSH 登录密码" />
            </el-form-item>
          </template>

          <!-- 内联私钥 -->
          <template v-if="serverForm.auth_type === 'key'">
            <el-form-item label="用户名" required>
              <el-input v-model="serverForm.auth_username" placeholder="SSH 登录用户名" />
            </el-form-item>
            <el-form-item label="私钥内容" required>
              <el-input v-model="serverForm.auth_private_key" type="textarea" :rows="4" placeholder="-----BEGIN OPENSSH PRIVATE KEY-----" />
            </el-form-item>
          </template>
          <el-form-item label="所属分组">
            <el-select v-model="serverGroupIds" multiple filterable placeholder="选择分组（留空则归入未分组）" style="width: 100%">
              <el-option v-for="g in groups" :key="g.id" :label="g.name" :value="g.id" />
            </el-select>
          </el-form-item>
          <el-form-item label="标签"><el-input v-model="tagsInput" placeholder="逗号分隔" /></el-form-item>
          <el-form-item label="备注"><el-input v-model="serverForm.comment" type="textarea" :rows="2" /></el-form-item>
        </el-form>
        <template #footer>
          <el-button @click="showAddServer = false">取消</el-button>
          <el-button type="primary" :loading="savingServer" @click="saveServer">{{ editingServerId ? '保存' : '添加' }}</el-button>
        </template>
      </el-dialog>

      <!-- Command Dialog -->
      <el-dialog v-model="showCommandDialog" title="执行命令" width="700px">
        <el-input v-model="commandInput" type="textarea" :rows="3" placeholder="输入要在所有服务器上执行的命令" />
        <div class="command-results" v-if="commandResults.length > 0" style="margin-top: 16px">
          <h4>执行结果</h4>
          <el-collapse>
            <el-collapse-item v-for="r in commandResults" :key="r.server_id" :name="r.server_id">
              <template #title>
                <span>
                  <el-tag :type="r.exit_code === 0 ? 'success' : 'danger'" size="small">{{ r.exit_code === 0 ? '成功' : '失败' }}</el-tag>
                  {{ r.hostname }} ({{ r.exit_code }})
                </span>
              </template>
              <pre class="command-output">{{ r.output || r.error }}</pre>
            </el-collapse-item>
          </el-collapse>
        </div>
        <template #footer>
          <el-button @click="showCommandDialog = false">关闭</el-button>
          <el-button type="primary" :loading="commandLoading" @click="executeCommand">执行</el-button>
        </template>
      </el-dialog>

      <!-- Import Dialog -->
      <el-dialog v-model="showImportDialog" title="导入服务器 (CSV)" width="640px">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px">
          <span style="font-weight: 600">CSV 字段说明</span>
          <el-button size="small" plain @click="downloadTemplate">
            <el-icon style="margin-right: 4px"><download /></el-icon>下载 CSV 模板
          </el-button>
        </div>
        <el-table :data="fieldDocs" size="small" border max-height="240" empty-text="暂无字段说明">
          <el-table-column prop="name" label="字段" width="150">
            <template #default="{ row }">
              <code>{{ row.name }}</code>
              <el-tag v-if="row.required" size="small" type="danger" style="margin-left: 4px">必填</el-tag>
              <el-tag v-else size="small" type="info" effect="plain">选填</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="desc" label="说明" min-width="300" />
        </el-table>
        <el-upload drag :auto-upload="false" :on-change="handleFileChange" :limit="1" accept=".csv" style="margin-top: 12px">
          <el-icon class="el-icon--upload"><upload-filled /></el-icon>
          <div class="el-upload__text">将 CSV 文件拖到此处，或<em>点击上传</em></div>
                    <template #tip>
                      <div class="el-upload__tip">
                        <div>支持 UTF-8 / GBK 编码的 CSV（Excel 中文环境可直接保存），必填列：hostname, ip</div>
                        <div style="color: #e6a23c">批量导入不支持私钥认证；仅填用户名+密码会自动按密码认证，无需写 auth_type</div>
                      </div>
                    </template>
        </el-upload>
        <template #footer>
          <el-button @click="showImportDialog = false">取消</el-button>
          <el-button type="primary" :loading="importing" @click="importServers" :disabled="!importFile">导入</el-button>
        </template>
      </el-dialog>

      <!-- Batch Credential Dialog -->
      <el-dialog v-model="showCredentialDialog" title="批量更新凭据" width="400px">
        <el-form label-width="80px">
          <el-form-item label="选择凭据">
            <div style="display: flex; gap: 8px; width: 100%">
              <el-select v-model="batchCredentialId" style="flex: 1">
                <el-option v-for="c in credentials" :key="c.id" :label="`${c.name} (${c.username}@${authTypeLabel(c.auth_type)})`" :value="c.id" />
              </el-select>
              <el-button type="primary" plain @click="openCredentialDialog()">新建</el-button>
              <el-button v-if="batchCredentialId" type="warning" plain @click="openCredentialDialog(credentials.find(c => c.id === batchCredentialId))">编辑</el-button>
            </div>
          </el-form-item>
          <el-alert
            v-if="credentials.length === 0"
            title="暂无凭据，请先新建凭据" type="warning" :closable="false" show-icon
          />
        </el-form>
        <template #footer>
          <el-button @click="showCredentialDialog = false">取消</el-button>
          <el-button type="primary" @click="confirmBatchCredential">确认</el-button>
        </template>
      </el-dialog>

      <!-- Credential Manage Dialog (Create / Edit) -->
      <el-dialog v-model="showCredentialManageDialog" :title="editingCredentialId ? '编辑凭据' : '新建凭据'" width="640px">
        <el-form :model="credentialForm" label-width="110px">
          <el-row :gutter="16">
            <el-col :span="12">
              <el-form-item label="凭据名称" required><el-input v-model="credentialForm.name" placeholder="如: 生产root密码" /></el-form-item>
            </el-col>
            <el-col :span="12">
              <el-form-item label="认证类型" required>
                <el-select v-model="credentialForm.auth_type" style="width: 100%">
                  <el-option label="密码" value="password" />
                  <el-option label="SSH密钥" value="key" />
                  <el-option label="SSH密钥+密码" value="key_with_passphrase" />
                  <el-option label="临时Token" value="token" />
                </el-select>
              </el-form-item>
            </el-col>
          </el-row>
          <el-form-item label="用户名" required><el-input v-model="credentialForm.username" placeholder="如: root" /></el-form-item>
          <el-form-item v-if="credentialForm.auth_type === 'password'" label="密码">
            <el-input v-model="credentialForm.password" type="password" show-password placeholder="登录密码" />
          </el-form-item>
          <el-form-item v-if="credentialForm.auth_type === 'key' || credentialForm.auth_type === 'key_with_passphrase'" label="私钥内容">
            <el-input v-model="credentialForm.private_key_content" type="textarea" :rows="4" placeholder="-----BEGIN OPENSSH PRIVATE KEY----- ..." />
          </el-form-item>
          <el-form-item v-if="credentialForm.auth_type === 'key_with_passphrase'" label="私钥密码">
            <el-input v-model="credentialForm.passphrase_content" type="password" show-password placeholder="私钥加密密码（如有）" />
          </el-form-item>
          <el-form-item v-if="credentialForm.auth_type === 'token'" label="临时Token">
            <el-input v-model="credentialForm.token_content" type="password" show-password placeholder="临时Token" />
          </el-form-item>
          <el-divider content-position="left">跳板机（可选）</el-divider>
          <el-row :gutter="16">
            <el-col :span="12">
              <el-form-item label="跳板机地址"><el-input v-model="credentialForm.jump_host" placeholder="如: bastion.example.com" /></el-form-item>
            </el-col>
            <el-col :span="6">
              <el-form-item label="端口"><el-input-number v-model="credentialForm.jump_port" :min="1" :max="65535" style="width: 100%" /></el-form-item>
            </el-col>
            <el-col :span="6">
              <el-form-item label="跳板用户"><el-input v-model="credentialForm.jump_username" placeholder="如: jumpuser" /></el-form-item>
            </el-col>
          </el-row>
          <el-form-item label="连接超时(秒)"><el-input-number v-model="credentialForm.connect_timeout" :min="1" :max="300" style="width: 100%" /></el-form-item>
        </el-form>
        <template #footer>
          <el-button @click="showCredentialManageDialog = false">取消</el-button>
          <el-button type="danger" plain v-if="editingCredentialId" @click="deleteCredential(editingCredentialId)">删除</el-button>
          <el-button type="primary" :loading="savingCredential" @click="saveCredential">{{ editingCredentialId ? '保存' : '创建' }}</el-button>
        </template>
      </el-dialog>

      <!-- Batch Group Dialog (Move / Add) -->
      <el-dialog v-model="showGroupDialog" :title="groupDialogTitle" width="460px">
        <el-form label-width="100px">
          <el-form-item label="已选服务器">
            <span>{{ selectedIds.size }} 台</span>
          </el-form-item>
          <el-form-item :label="groupMode === 'move' ? '目标分组' : '添加到分组'">
            <el-select v-model="batchGroupIds" multiple filterable placeholder="选择目标分组" style="width: 100%">
              <el-option v-for="g in groups" :key="g.id" :label="g.name" :value="g.id" />
            </el-select>
          </el-form-item>
          <el-alert
            v-if="groupMode === 'move'"
            title="移动分组将替换所选服务器的所有现有分组"
            type="warning" :closable="false" show-icon
            style="margin-top: 8px"
          />
          <el-alert
            v-else
            title="增加分组将保留现有分组，并追加新的分组"
            type="info" :closable="false" show-icon
            style="margin-top: 8px"
          />
        </el-form>
        <template #footer>
          <el-button @click="showGroupDialog = false">取消</el-button>
          <el-button type="primary" :loading="groupOperationLoading" @click="confirmBatchGroup">确认</el-button>
        </template>
      </el-dialog>
    </div>
  </AppLayout>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted, watch, nextTick } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { ArrowDown, UploadFilled, Download, Search, MoreFilled } from '@element-plus/icons-vue'
import AppLayout from '@/components/AppLayout.vue'
import { serverApi, type ServerGroup, type Server } from '@/api/server'
import { authApi, type SSHCredential } from '@/api/auth'

const groups = ref<ServerGroup[]>([])
const servers = ref<Server[]>([])
const credentials = ref<SSHCredential[]>([])
const selectedGroupId = ref('')
// 分组搜索（前端过滤）
const groupSearch = ref('')
const filteredGroups = computed(() => {
  const q = groupSearch.value.trim().toLowerCase()
  if (!q) return groups.value
  return groups.value.filter((g) => g.name.toLowerCase().includes(q))
})

// 分组更多操作下拉菜单
function handleGroupCommand(command: string, group: ServerGroup) {
  if (command === 'detail') showGroupDetail(group)
  else if (command === 'edit') editGroup(group)
  else if (command === 'delete') deleteGroupConfirm(group)
}
// 选中集合为唯一事实源（跨页保留）；selectedServers 仅反映当前页勾选
const selectedServers = ref<Server[]>([])
const selectedIds = ref<Set<string>>(new Set())
const serversLoading = ref(false)
// 分页：pageSize=0 表示全部
const pageSize = ref(20)
const currentPage = ref(1)
const tableRef = ref<any>()

// 主机搜索（主机名/IP/标签，支持模糊/精确）
const serverSearch = ref('')
const searchMode = ref<'fuzzy' | 'exact'>('fuzzy')
// 列过滤状态（columnKey -> 选中值列表，由 el-table filter-change 维护）
const activeFilters = ref<Record<string, string[]>>({})

function handleFilterChange(filters: Record<string, string[]>) {
  for (const key of Object.keys(filters)) {
    activeFilters.value[key] = filters[key] || []
  }
  currentPage.value = 1
}

// 列过滤选项（基于当前数据动态生成）
const portFilters = computed(() => [...new Set(servers.value.map(s => String(s.ssh_port || 22)))].sort().map(v => ({ text: v, value: v })))
const protocolFilters = computed(() => [...new Set(servers.value.map(s => (s.protocol || 'ssh').toLowerCase()))].map(v => ({ text: v.toUpperCase(), value: v })))
const platformFilters = computed(() => [...new Set(servers.value.map(s => s.platform || 'linux'))].map(v => ({ text: platformLabel(v), value: v })))
const connectivityFilters = computed(() => {
  const present = new Set<string>(servers.value.map(s => s.connectivity_status || 'unknown'))
  return [
    { text: '连通', value: 'success' },
    { text: '失败', value: 'failed' },
    { text: '未知', value: 'unknown' },
  ].filter(f => present.has(f.value))
})
const groupFilters = computed(() => {
  const names = new Set<string>()
  let hasUngrouped = false
  for (const s of servers.value) {
    if (!s.groups || s.groups.length === 0) { hasUngrouped = true; continue }
    s.groups.forEach(g => names.add(g.name))
  }
  const opts = [...names].sort().map(n => ({ text: n, value: n }))
  if (hasUngrouped) opts.push({ text: '未分组', value: '__ungrouped__' })
  return opts
})
const tagFilters = computed(() => [...new Set(servers.value.flatMap(s => s.tags || []))].sort().map(t => ({ text: t, value: t })))

// 搜索 + 列过滤后的列表（全局过滤，再分页）
const filteredServers = computed(() => {
  let list = servers.value
  const q = serverSearch.value.trim().toLowerCase()
  if (q) {
    list = list.filter(s => {
      const fields = [s.hostname || '', s.ip || '', ...(s.tags || [])].map(f => f.toLowerCase())
      return searchMode.value === 'exact'
        ? fields.some(f => f === q)
        : fields.some(f => f.includes(q))
    })
  }
  const f = activeFilters.value
  if (f.ssh_port?.length) list = list.filter(s => f.ssh_port.includes(String(s.ssh_port || 22)))
  if (f.protocol?.length) list = list.filter(s => f.protocol.includes((s.protocol || 'ssh').toLowerCase()))
  if (f.platform?.length) list = list.filter(s => f.platform.includes(s.platform || 'linux'))
  if (f.connectivity_status?.length) list = list.filter(s => f.connectivity_status.includes(s.connectivity_status || 'unknown'))
  if (f.groups?.length) {
    list = list.filter(s => {
      const ungrouped = !s.groups || s.groups.length === 0
      if (ungrouped) return f.groups.includes('__ungrouped__')
      return s.groups.some(g => f.groups.includes(g.name))
    })
  }
  if (f.tags?.length) list = list.filter(s => (s.tags || []).some(t => f.tags.includes(t)))
  return list
})

// 搜索/模式变化时回到第一页
watch([serverSearch, searchMode], () => { currentPage.value = 1 })

const pagedServers = computed(() => {
  if (pageSize.value === 0) return filteredServers.value
  const start = (currentPage.value - 1) * pageSize.value
  return filteredServers.value.slice(start, start + pageSize.value)
})

const isAllSelected = computed(() => servers.value.length > 0 && servers.value.every(s => selectedIds.value.has(s.id)))
const isPartialSelected = computed(() => selectedIds.value.size > 0 && !isAllSelected.value)

function handlePageChange(page: number) {
  currentPage.value = page
}

function handlePageSizeChange(size: number) {
  pageSize.value = size
  currentPage.value = 1
}

// 切页/改每页条数后，回填属于选中集合的行勾选状态（视觉与数量一致）
watch([currentPage, pageSize], () => {
  nextTick(() => {
    if (!tableRef.value) return
    pagedServers.value.forEach(s => {
      if (selectedIds.value.has(s.id)) tableRef.value.toggleRowSelection(s, true)
    })
  })
})

// 表头全选：选中当前分组下全部服务器（跨页）
function toggleSelectAll(checked: boolean | string | number) {
  if (checked) {
    selectedIds.value = new Set(servers.value.map(s => s.id))
    tableRef.value?.toggleAllSelection()
  } else {
    selectedIds.value = new Set()
    tableRef.value?.clearSelection()
  }
}

function clearSelection() {
  selectedIds.value = new Set()
  selectedServers.value = []
  tableRef.value?.clearSelection()
}

function selectedServerObjects(): Server[] {
  return servers.value.filter(s => selectedIds.value.has(s.id))
}
const selectedGroup = computed(() => {
  // __all__ 为全局视图的虚拟分组
  if (selectedGroupId.value === '__all__') {
    return { id: '__all__', name: '全部服务器' } as unknown as ServerGroup
  }
  return groups.value.find((g) => g.id === selectedGroupId.value)
})
const isGlobalView = computed(() => selectedGroupId.value === '__all__')
const totalServerCount = computed(() => groups.value.reduce((sum, g) => sum + (g.server_count || 0), 0))

const showCreateGroup = ref(false)
const creating = ref(false)
const editingGroupId = ref<string | null>(null)
const groupForm = reactive({
  name: '', description: '', default_credential: null as string | null, auto_patrol: true,
})
const showGroupDetailDrawer = ref(false)
const detailGroup = ref<ServerGroup | null>(null)

const showAddServer = ref(false)
const editingServerId = ref<string | null>(null)
const savingServer = ref(false)
const serverForm = reactive({
  hostname: '', ip: '', ssh_port: 22, protocol: 'ssh' as Server['protocol'], platform: 'linux' as Server['platform'],
  connect_timeout: 15, exec_timeout: 600, comment: '', ssh_credential: null as string | null,
  auth_type: 'credential' as string, auth_username: '', auth_password: '', auth_private_key: '',
})
const tagsInput = ref('')
const serverGroupIds = ref<string[]>([])

const connectivityLoading = ref(false)
const showCommandDialog = ref(false)
const commandInput = ref('')
const commandLoading = ref(false)
const commandResults = ref<any[]>([])

const showImportDialog = ref(false)
const importFile = ref<File | null>(null)
const importing = ref(false)

// CSV 字段说明（与后端 batch.py 解析规则一致）
const fieldDocs = [
  { name: 'hostname', required: true, desc: '主机名（支持中文）' },
  { name: 'ip', required: true, desc: 'IP 地址，全局唯一，重复会报错' },
  { name: 'auth_type', required: false, desc: '认证方式：password / credential；留空但填写了用户名+密码时自动按密码认证' },
  { name: 'auth_username', required: false, desc: '认证用户名（密码认证时必填）' },
  { name: 'auth_password', required: false, desc: '认证密码（密码认证时必填，入库加密存储）' },
  { name: 'labels', required: false, desc: '标签，逗号分隔可填多个，如：生产,高优' },
  { name: 'tags', required: false, desc: '附加标签，逗号分隔可填多个，如：nginx,db' },
  { name: 'groups', required: false, desc: '分组名，逗号分隔；不存在时自动创建，如：web,db' },
  { name: 'ssh_port', required: false, desc: 'SSH 端口，默认 22' },
  { name: 'protocol', required: false, desc: '连接协议，默认 ssh' },
  { name: 'platform', required: false, desc: '系统平台，默认 linux' },
  { name: 'comment', required: false, desc: '备注（支持中文）' },
]

// 下载 CSV 模板（UTF-8 BOM，Excel 可直接打开；含一行示例数据）
function downloadTemplate() {
  const header = 'hostname,ip,auth_type,auth_username,auth_password,labels,tags,groups,ssh_port,protocol,platform,comment'
  const sample = 'web-01,10.20.1.10,,root,MyPass@123,生产环境,nginx,web,22,ssh,linux,示例行：支持中文与多值标签'
  const blob = new Blob([`\uFEFF${header}\n${sample}\n`], { type: 'text/csv;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = 'servers_import_template.csv'
  a.click()
  URL.revokeObjectURL(url)
}

const showCredentialDialog = ref(false)
const batchCredentialId = ref('')

// Credential manage dialog
const showCredentialManageDialog = ref(false)
const editingCredentialId = ref<string | null>(null)
const savingCredential = ref(false)
const credentialForm = reactive({
  name: '', auth_type: 'password' as SSHCredential['auth_type'], username: '',
  password: '', private_key_content: '', passphrase_content: '', token_content: '',
  jump_host: '', jump_port: 22, jump_username: '', connect_timeout: 15,
})

// Server detail drawer
const showDetailDrawer = ref(false)
const detailServer = ref<Server | null>(null)

// Batch group dialog
const showGroupDialog = ref(false)
const groupMode = ref<'move' | 'add'>('move')
const batchGroupIds = ref<string[]>([])
const groupOperationLoading = ref(false)
const groupDialogTitle = computed(() => groupMode.value === 'move' ? '移动分组' : '增加分组')

onMounted(async () => {
  await loadGroups()
  await loadCredentials()
})

async function loadGroups() {
  const { data } = await serverApi.listGroups()
  groups.value = Array.isArray(data) ? data : (data as any).results || []
  if (groups.value.length > 0 && !selectedGroupId.value) {
    selectGroup(groups.value[0].id)
  }
}

async function loadCredentials() {
  try {
    const { data } = await authApi.listCredentials()
    credentials.value = Array.isArray(data) ? data : (data as any).results || []
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail || '凭据加载失败')
  }
}

function openCredentialDialog(credential?: SSHCredential) {
  editingCredentialId.value = credential?.id || null
  credentialForm.name = credential?.name || ''
  credentialForm.auth_type = credential?.auth_type || 'password'
  credentialForm.username = credential?.username || ''
  credentialForm.password = ''
  credentialForm.private_key_content = ''
  credentialForm.passphrase_content = ''
  credentialForm.token_content = ''
  credentialForm.jump_host = credential?.jump_host || ''
  credentialForm.jump_port = credential?.jump_port || 22
  credentialForm.jump_username = credential?.jump_username || ''
  credentialForm.connect_timeout = credential?.connect_timeout || 15
  showCredentialManageDialog.value = true
}

async function saveCredential() {
  if (!credentialForm.name.trim()) { ElMessage.warning('请输入凭据名称'); return }
  if (!credentialForm.username.trim()) { ElMessage.warning('请输入用户名'); return }
  savingCredential.value = true
  try {
    const payload: any = {
      name: credentialForm.name.trim(),
      auth_type: credentialForm.auth_type,
      username: credentialForm.username.trim(),
      jump_host: credentialForm.jump_host,
      jump_port: credentialForm.jump_port,
      jump_username: credentialForm.jump_username,
      connect_timeout: credentialForm.connect_timeout,
    }
    if (credentialForm.password) payload.password = credentialForm.password
    if (credentialForm.private_key_content) payload.private_key_content = credentialForm.private_key_content
    if (credentialForm.passphrase_content) payload.passphrase_content = credentialForm.passphrase_content
    if (credentialForm.token_content) payload.token_content = credentialForm.token_content

    if (editingCredentialId.value) {
      await authApi.updateCredential(editingCredentialId.value, payload)
      ElMessage.success('凭据已更新')
    } else {
      const { data } = await authApi.createCredential(payload)
      // 新建后自动选中该凭据
      serverForm.ssh_credential = data.id
      batchCredentialId.value = data.id
      ElMessage.success('凭据创建成功')
    }
    showCredentialManageDialog.value = false
    await loadCredentials()
  } catch (e: any) {
    const status = e.response?.status
    const detail = e.response?.data?.detail
    ElMessage.error(detail || (status ? `凭据保存失败 (HTTP ${status})` : '凭据保存失败，请检查网络'))
  } finally { savingCredential.value = false }
}

async function deleteCredential(id: string) {
  await ElMessageBox.confirm('确定删除此凭据？已关联的服务器将使用分组默认凭据', '删除凭据', { type: 'warning' })
  await authApi.deleteCredential(id)
  ElMessage.success('凭据已删除')
  showCredentialManageDialog.value = false
  editingCredentialId.value = null
  if (serverForm.ssh_credential === id) serverForm.ssh_credential = null
  await loadCredentials()
}

function authTypeLabel(t: string) {
  const map: Record<string, string> = { password: '密码', key: '密钥', key_with_passphrase: '密钥+密码', token: 'Token' }
  return map[t] || t
}

function credentialName(id: string | null | undefined) {
  if (!id) return '分组默认'
  const c = credentials.value.find((x) => x.id === id)
  return c ? `${c.name} (${c.username}@${authTypeLabel(c.auth_type)})` : '未知'
}

async function selectGroup(groupId: string) {
  selectedGroupId.value = groupId
  clearSelection()
  currentPage.value = 1
  // 切换分组/全局视图时重置搜索与列过滤
  serverSearch.value = ''
  activeFilters.value = {}
  tableRef.value?.clearFilter()
  serversLoading.value = true
  try {
    // __all__ 为全局视图：加载租户下全部服务器
    const { data } = groupId === '__all__'
      ? await serverApi.listAllServers()
      : await serverApi.listServers(groupId)
    servers.value = Array.isArray(data) ? data : (data as any).results || []
  } finally { serversLoading.value = false }
}

function handleSelectionChange(selection: Server[]) {
  selectedServers.value = selection
  // 增量合并：当前页取消勾选的行从集合移除，勾选的行加入集合（其他页不受影响）
  const selIds = new Set(selection.map(s => s.id))
  const next = new Set(selectedIds.value)
  for (const s of pagedServers.value) {
    if (!selIds.has(s.id)) next.delete(s.id)
  }
  for (const s of selection) next.add(s.id)
  selectedIds.value = next
}

function showServerDetail(row: Server) {
  detailServer.value = row
  showDetailDrawer.value = true
}

function openCreateGroup() {
  editingGroupId.value = null
  groupForm.name = ''
  groupForm.description = ''
  groupForm.default_credential = null
  groupForm.auto_patrol = true
  showCreateGroup.value = true
}

function editGroup(group: ServerGroup) {
  editingGroupId.value = group.id
  groupForm.name = group.name
  groupForm.description = group.description || ''
  groupForm.default_credential = group.default_credential || null
  groupForm.auto_patrol = group.auto_patrol !== false
  showCreateGroup.value = true
}

function closeGroupDialog() {
  showCreateGroup.value = false
  editingGroupId.value = null
}

async function saveGroup() {
  if (!groupForm.name.trim()) { ElMessage.warning('请输入分组名称'); return }
  creating.value = true
  try {
    const payload = {
      name: groupForm.name.trim(),
      description: groupForm.description,
      default_credential: groupForm.default_credential,
      auto_patrol: groupForm.auto_patrol,
    }
    if (editingGroupId.value) {
      await serverApi.updateGroup(editingGroupId.value, payload)
      ElMessage.success('分组已更新')
    } else {
      await serverApi.createGroup(payload)
      ElMessage.success('分组创建成功')
    }
    closeGroupDialog()
    await loadGroups()
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail || '分组保存失败')
  } finally { creating.value = false }
}

async function deleteGroupConfirm(group: ServerGroup) {
  try {
    await ElMessageBox.confirm(
      `删除分组「${group.name}」？组内 ${group.server_count} 台服务器将自动归入"未分组"。`,
      '删除分组', { type: 'warning' },
    )
  } catch {
    return  // 用户取消
  }
  await serverApi.deleteGroup(group.id)
  ElMessage.success('分组已删除')
  if (selectedGroupId.value === group.id) selectedGroupId.value = ''
  await loadGroups()
}

async function showGroupDetail(group: ServerGroup) {
  try {
    const { data } = await serverApi.getGroup(group.id)
    detailGroup.value = data
    showGroupDetailDrawer.value = true
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail || '分组详情加载失败')
  }
}

function editServer(server: Server) {
  editingServerId.value = server.id
  serverForm.hostname = server.hostname
  serverForm.ip = server.ip
  serverForm.ssh_port = server.ssh_port
  serverForm.protocol = server.protocol || 'ssh'
  serverForm.platform = server.platform || 'linux'
  serverForm.connect_timeout = server.connect_timeout || 15
  serverForm.exec_timeout = server.exec_timeout || 600
  serverForm.comment = server.comment || ''
  serverForm.ssh_credential = server.ssh_credential || null
  serverForm.auth_type = (server as any).auth_type || 'credential'
  serverForm.auth_username = (server as any).auth_username || ''
  serverForm.auth_password = ''
  serverForm.auth_private_key = ''
  tagsInput.value = (server.tags || []).join(', ')
  serverGroupIds.value = (server.groups || []).map(g => g.id)
  showAddServer.value = true
}

async function saveServer() {
  savingServer.value = true
  try {
    const payload = {
      ...serverForm,
      tags: tagsInput.value.split(',').map(t => t.trim()).filter(Boolean),
      group_ids: serverGroupIds.value,
    }
    if (editingServerId.value) {
      await serverApi.updateServer(editingServerId.value, payload)
      ElMessage.success('服务器已更新')
    } else {
      const { data } = await serverApi.batchCreateServers(selectedGroupId.value, [payload])
      if (data.errors && data.errors.length > 0) {
        ElMessage.error(data.errors[0].error || '添加失败')
        return
      }
      ElMessage.success('服务器已添加')
    }
    showAddServer.value = false
    editingServerId.value = null
    resetServerForm()
    await selectGroup(selectedGroupId.value)
    await loadGroups()
  } finally { savingServer.value = false }
}

function resetServerForm() {
  serverForm.hostname = ''; serverForm.ip = ''; serverForm.ssh_port = 22
  serverForm.protocol = 'ssh'; serverForm.platform = 'linux'
  serverForm.connect_timeout = 15; serverForm.exec_timeout = 600
  serverForm.comment = ''; tagsInput.value = ''; serverGroupIds.value = []
  serverForm.ssh_credential = null
  serverForm.auth_type = 'credential'
  serverForm.auth_username = ''; serverForm.auth_password = ''; serverForm.auth_private_key = ''
}

async function deleteServer(id: string) {
  await ElMessageBox.confirm('确定删除此服务器？')
  await serverApi.deleteServer(id)
  ElMessage.success('已删除')
  await selectGroup(selectedGroupId.value)
  await loadGroups()
}

async function checkConnectivity() {
  if (!selectedGroupId.value) return
  connectivityLoading.value = true
  try {
    const { data } = await serverApi.checkConnectivity(selectedGroupId.value)
    const results = Array.isArray(data) ? data : (data as any).results || []
    const ok = results.filter((r: any) => r.status === 'success').length
    ElMessage.success(`连通性检测完成: ${ok}/${results.length} 台成功`)
    await selectGroup(selectedGroupId.value)
  } finally { connectivityLoading.value = false }
}

async function executeCommand() {
  if (!selectedGroupId.value || !commandInput.value) return
  commandLoading.value = true
  try {
    const { data } = await serverApi.executeCommand(selectedGroupId.value, commandInput.value)
    commandResults.value = Array.isArray(data) ? data : (data as any).results || []
  } finally { commandLoading.value = false }
}

function handleBatchCommand(command: string) {
  if (command === 'connectivity') {
    batchConnectivity()
  } else if (command === 'credential') {
    showCredentialDialog.value = true
  } else if (command === 'delete') {
    batchDelete()
  } else if (command === 'group-move') {
    groupMode.value = 'move'
    batchGroupIds.value = []
    showGroupDialog.value = true
  } else if (command === 'group-add') {
    groupMode.value = 'add'
    batchGroupIds.value = []
    showGroupDialog.value = true
  }
}

async function batchConnectivity() {
  const ids = selectedServerObjects().map(s => s.id)
  try {
    const { data } = await serverApi.batchConnectivity(ids)
    const ok = (data.results || []).filter((r: any) => r.status === 'success').length
    ElMessage.success(`批量连通性测试: ${ok}/${ids.length} 台成功`)
    await selectGroup(selectedGroupId.value)
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail || '批量测试失败')
  }
}

async function confirmBatchCredential() {
  if (!batchCredentialId.value) { ElMessage.warning('请选择凭据'); return }
  const ids = selectedServerObjects().map(s => s.id)
  try {
    const { data } = await serverApi.batchUpdateCredential(ids, batchCredentialId.value)
    ElMessage.success(`已更新 ${data.updated} 台服务器凭据`)
    showCredentialDialog.value = false
    await selectGroup(selectedGroupId.value)
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail || '批量更新失败')
  }
}

async function batchDelete() {
  const targets = selectedServerObjects()
  await ElMessageBox.confirm(`确定删除选中的 ${targets.length} 台服务器？`)
  const ids = targets.map(s => s.id)
  try {
    const { data } = await serverApi.batchDelete(ids)
    ElMessage.success(`已删除 ${data.deleted} 台服务器`)
    clearSelection()
    await selectGroup(selectedGroupId.value)
    await loadGroups()
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail || '批量删除失败')
  }
}

async function confirmBatchGroup() {
  if (batchGroupIds.value.length === 0) {
    ElMessage.warning('请选择目标分组')
    return
  }
  const serverIds = selectedServerObjects().map(s => s.id)
  groupOperationLoading.value = true
  try {
    if (groupMode.value === 'move') {
      const { data } = await serverApi.batchGroupMove(serverIds, batchGroupIds.value)
      ElMessage.success(`已移动 ${data.updated} 台服务器`)
    } else {
      const { data } = await serverApi.batchGroupAdd(serverIds, batchGroupIds.value)
      ElMessage.success(`已为 ${data.updated} 台服务器添加分组`)
    }
    showGroupDialog.value = false
    clearSelection()
    await selectGroup(selectedGroupId.value)
    await loadGroups()
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail || '批量分组操作失败')
  } finally { groupOperationLoading.value = false }
}

function handleFileChange(file: any) {
  importFile.value = file.raw
}

async function importServers() {
  if (!importFile.value) return
  importing.value = true
  try {
    const { data } = await serverApi.importServers(selectedGroupId.value, importFile.value)
    ElMessage.success(`导入完成: 成功 ${data.created} 台, 失败 ${data.errors?.length || 0} 台`)
    showImportDialog.value = false
    importFile.value = null
    await selectGroup(selectedGroupId.value)
    await loadGroups()
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail || '导入失败')
  } finally { importing.value = false }
}

async function exportServers() {
  try {
    const { data } = await serverApi.exportServers(selectedGroupId.value)
    const blob = new Blob([data], { type: 'text/csv' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `servers_${selectedGroup.value?.name}.csv`
    a.click()
    URL.revokeObjectURL(url)
  } catch {
    ElMessage.error('导出失败')
  }
}

function statusType(s: string) { return s === 'success' ? 'success' : s === 'failed' ? 'danger' : 'info' }
function statusLabel(s: string) { return s === 'success' ? '连通' : s === 'failed' ? '失败' : '未知' }
function platformLabel(p: string) {
  const map: Record<string, string> = { linux: 'Linux', windows: 'Windows', unix: 'Unix', network: '网络设备', other: '其他' }
  return map[p] || p
}
</script>

<style scoped>
.servers-page { display: flex; gap: 16px; padding: 16px; }
.group-panel { width: 280px; flex-shrink: 0; }
.server-panel { flex: 1; }
.panel-header { display: flex; justify-content: space-between; align-items: center; }
.header-actions { display: flex; gap: 8px; align-items: center; }
.group-item { display: flex; align-items: center; gap: 8px; }
.group-name { cursor: pointer; flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.group-actions { display: flex; gap: 4px; opacity: 0; transition: opacity 0.15s; }
.group-item:hover .group-actions { opacity: 1; }
.group-action { cursor: pointer; color: #909399; }
.group-action:hover { color: #409eff; }
.group-action:last-child:hover { color: #f56c6c; }
.group-item :deep(.el-badge__content) { vertical-align: middle; top: 0; }
.command-output {
  background: #1e1e1e; color: #d4d4d4; padding: 12px; border-radius: 4px;
  overflow-x: auto; font-size: 13px; line-height: 1.5; white-space: pre-wrap;
}
.detail-groups { display: flex; flex-wrap: wrap; }
</style>

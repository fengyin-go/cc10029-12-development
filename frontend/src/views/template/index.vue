<template>
  <section class="page" data-module="template">
    <header class="page-head">
      <div>
        <h2>模板市场管理</h2>
        <p class="page-desc">管理可复用的站点采集模板，按站点类型分类和版本控制。</p>
      </div>
      <div class="page-actions">
        <button class="btn primary" data-testid="open-create" type="button" @click="openCreate">登记采集模板</button>
        <button class="btn" data-testid="export" type="button" @click="exportRows">导出模板市场清单</button>
      </div>
    </header>

    <div class="stat-row">
      <article v-for="item in stats" :key="item.label" class="stat-card">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ item.value }}</strong>
      </article>
    </div>

    <form class="filter-bar" @submit.prevent="reload">
      <label v-for="field in filterFields" :key="field" class="filter-item">
        <span>{{ field }}</span>
        <input v-model="filters[field]" :data-testid="`filter-${field}`" :placeholder="`按${field}检索`" />
      </label>
      <button class="btn" data-testid="query" type="submit">查询</button>
      <button class="btn ghost" data-testid="reset" type="button" @click="resetFilters">重置条件</button>
    </form>

    <table class="data-table">
      <thead>
        <tr>
          <th v-for="column in columns" :key="column">{{ column }}</th>
          <th>可执行动作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in rows" :key="String(row.id)" :data-testid="`row-${row.id}`" :data-status="String(row.status)">
          <td v-for="column in columns" :key="column">{{ row[column] ?? '—' }}</td>
          <td class="row-actions">
            <button
              v-for="action in actions"
              :key="action"
              class="link"
              type="button"
              :data-testid="`action-${row.id}-${action}`"
              @click="runAction(action, row)"
            >
              {{ action }}
            </button>
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td :colspan="columns.length + 1" class="empty-state">暂无模板市场数据，可先登记采集模板</td>
        </tr>
      </tbody>
    </table>

    <div v-if="showCreate" class="modal-backdrop" data-testid="create-modal">
      <form class="modal" @submit.prevent="submitCreate">
        <h3>登记采集模板</h3>
        <label v-for="field in columns" :key="field" class="create-field">
          <span>{{ field }}</span>
          <input v-model="createValues[field]" :data-testid="`create-${field}`" required />
        </label>
        <div class="page-actions">
          <button class="btn" type="button" @click="showCreate = false">取消</button>
          <button class="btn primary" data-testid="submit-create" type="submit" :disabled="creating">
            {{ creating ? '提交中…' : '确认登记' }}
          </button>
        </div>
      </form>
    </div>

    <section class="version-dataset" data-testid="version-dataset">
      <header class="page-head">
        <div>
          <h3>受控模板版本数据集</h3>
          <p class="page-desc">
            按作者来源与适用站点计算授权范围，草稿、共享与已启用版本遵守同一归属规则；缺少授权关系的模板不能进入共享范围。
          </p>
        </div>
        <div class="page-actions">
          <button class="btn primary" data-testid="generate-versions" type="button" @click="generateVersions">
            计算授权范围并生成数据集
          </button>
        </div>
      </header>

      <div class="identity-bar">
        <label class="filter-item">
          <span>当前账户</span>
          <input v-model="identity.account" data-testid="identity-account" placeholder="当前账户" />
        </label>
        <label class="filter-item">
          <span>当前团队</span>
          <input v-model="identity.team" data-testid="identity-team" placeholder="当前团队" />
        </label>
        <button class="btn" data-testid="apply-identity" type="button" @click="loadVersions">应用身份</button>
        <span class="identity-hint">模板市场只允许本团队维护，其他账户只能查看</span>
      </div>

      <form class="filter-bar" @submit.prevent="loadVersions">
        <label class="filter-item">
          <span>适用站点</span>
          <input v-model="versionFilters['适用站点']" data-testid="filter-version-适用站点" placeholder="按站点查看模板作者、版本和共享范围" />
        </label>
        <label class="filter-item">
          <span>作者来源</span>
          <input v-model="versionFilters['作者来源']" data-testid="filter-version-作者来源" placeholder="按作者来源检索" />
        </label>
        <button class="btn" data-testid="query-versions" type="submit">查询</button>
        <button class="btn ghost" data-testid="reset-versions" type="button" @click="resetVersionFilters">重置条件</button>
      </form>

      <table class="data-table">
        <thead>
          <tr>
            <th v-for="column in versionColumns" :key="column">{{ column }}</th>
            <th>编辑权限</th>
            <th>可执行动作</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="version in versions"
            :key="String(version.id)"
            :data-testid="`version-row-${version.id}`"
            :data-readable="String(version['可读'])"
            :data-status="String(version.status)"
          >
            <td v-for="column in versionColumns" :key="column">{{ formatCell(version[column]) }}</td>
            <td :data-testid="`version-edit-${version.id}`">{{ version['编辑权限'] }}</td>
            <td class="row-actions">
              <button
                v-for="action in versionActions"
                :key="action"
                class="link"
                type="button"
                :data-testid="`version-action-${version.id}-${action}`"
                @click="runVersionAction(action, version)"
              >
                {{ action }}
              </button>
              <button
                class="link"
                type="button"
                :data-testid="`version-transfer-${version.id}`"
                @click="openTransfer(version)"
              >
                作者转移
              </button>
            </td>
          </tr>
          <tr v-if="!versions.length">
            <td :colspan="versionColumns.length + 2" class="empty-state">
              暂无受控模板版本数据，请先计算授权范围并生成数据集
            </td>
          </tr>
        </tbody>
      </table>

      <div v-if="showTransfer" class="modal-backdrop" data-testid="transfer-modal">
        <form class="modal" @submit.prevent="submitTransfer">
          <h3>作者转移 · {{ transferTarget?.['模板编号'] }}</h3>
          <p class="page-desc">
            转移后历史版本仍归原作者只读，新版本只能由当前作者或授权管理员修改。
          </p>
          <label class="create-field">
            <span>新作者</span>
            <input v-model="transferAuthor" data-testid="transfer-新作者" required placeholder="请输入新作者" />
          </label>
          <div class="page-actions">
            <button class="btn" type="button" @click="showTransfer = false">取消</button>
            <button class="btn primary" data-testid="submit-transfer" type="submit" :disabled="transferring">
              {{ transferring ? '转移中…' : '确认转移' }}
            </button>
          </div>
        </form>
      </div>

      <footer class="page-foot">
        <span>共 {{ versionTotal }} 条受控模板版本记录</span>
        <span v-if="versionMessage" class="error-text" data-testid="version-message">{{ versionMessage }}</span>
      </footer>
    </section>

    <footer class="page-foot">
      <span>共 {{ total }} 条模板市场记录</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import { request } from '@/api/client'
import { useSessionStore } from '@/stores/session'

type Row = Record<string, string | number | null>

const ENDPOINT = '/api/template'
const columns = ["模板编号", "模板名称", "适用站点", "站点类型", "提取逻辑", "内置规则", "使用次数", "作者来源"]
const actions = ["提交校验", "启用配置", "停用配置"]
const statuses = ["草稿", "待校验", "已启用", "已停用"]
const metricNames = ["采集模板总数", "待校验采集模板", "已启用采集模板"]

const session = useSessionStore()

// 受控模板版本数据集：沿用模板市场既有字段名，新增字段只追加
const versionColumns = ["模板编号", "模板名称", "版本号", "适用站点", "作者来源", "原作者", "当前作者", "共享范围", "授权团队", "责任边界", "授权状态", "历史版本", "status"]
const versionActions = ["提交校验", "启用配置", "停用配置"]

const rows = ref<Row[]>([])
const total = ref(0)
const errorMessage = ref('')
const filters = ref<Record<string, string>>({})
const filterFields = columns.slice(0, 3)
const showCreate = ref(false)
const creating = ref(false)
const createValues = ref<Record<string, string>>({})
const stats = computed(() => [
  { label: metricNames[0], value: total.value },
  { label: metricNames[1], value: rows.value.filter((row) => row.status === statuses[1]).length },
  { label: metricNames[2], value: rows.value.filter((row) => row.status === statuses[statuses.length - 1]).length },
])

// 受控模板版本数据集状态
const versions = ref<Row[]>([])
const versionTotal = ref(0)
const versionMessage = ref('')
const versionFilters = ref<Record<string, string>>({ '适用站点': '', '作者来源': '' })
const identity = ref({ account: session.operator, team: session.team })
const showTransfer = ref(false)
const transferring = ref(false)
const transferTarget = ref<Row | null>(null)
const transferAuthor = ref('')

function formatCell(value: unknown) {
  if (value === null || value === undefined || value === '') return '—'
  if (value === true) return '是'
  if (value === false) return '否'
  return String(value)
}

function identityQuery() {
  return { account: identity.value.account, team: identity.value.team }
}

async function loadVersions() {
  versionMessage.value = ''
  const query = new URLSearchParams({
    ...Object.fromEntries(Object.entries(versionFilters.value).filter(([, v]) => v)),
    ...identityQuery(),
  }).toString()
  try {
    const response = await request(`${ENDPOINT}/versions?${query}`)
    const payload = await response.json()
    versions.value = payload.items ?? []
    versionTotal.value = payload.total ?? versions.value.length
  } catch (error) {
    versionMessage.value = error instanceof Error ? error.message : '受控模板版本数据集读取失败'
  }
}

function resetVersionFilters() {
  versionFilters.value = { '适用站点': '', '作者来源': '' }
  void loadVersions()
}

async function generateVersions() {
  versionMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/versions/generate`, {
      method: 'POST', body: JSON.stringify(identityQuery()),
    })
    const payload = await response.json()
    await loadVersions()
    versionMessage.value = payload.message || ''
  } catch (error) {
    versionMessage.value = error instanceof Error ? error.message : '生成受控模板版本数据集失败'
  }
}

async function runVersionAction(action: string, version: Row) {
  versionMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/versions/${version.id}/actions`, {
      method: 'POST', body: JSON.stringify({ action, ...identityQuery() }),
    })
    const payload = await response.json()
    await loadVersions()
    versionMessage.value = payload.message || ''
  } catch (error) {
    versionMessage.value = error instanceof Error ? error.message : '受控模板版本操作失败'
  }
}

function openTransfer(version: Row) {
  transferTarget.value = version
  transferAuthor.value = ''
  versionMessage.value = ''
  showTransfer.value = true
}

async function submitTransfer() {
  if (!transferTarget.value) return
  transferring.value = true
  versionMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/versions/transfer`, {
      method: 'POST',
      body: JSON.stringify({
        '模板编号': transferTarget.value['模板编号'],
        '新作者': transferAuthor.value,
        ...identityQuery(),
      }),
    })
    const payload = await response.json()
    if (payload.ok) showTransfer.value = false
    await loadVersions()
    versionMessage.value = payload.message || ''
  } catch (error) {
    versionMessage.value = error instanceof Error ? error.message : '作者转移失败'
  } finally {
    transferring.value = false
  }
}

function resetFilters() {
  filters.value = {}
  void reload()
}

async function exportRows() {
  errorMessage.value = ''
  const query = new URLSearchParams(filters.value).toString()
  try {
    const response = await request(`${ENDPOINT}/export?${query}`)
    if (!response.ok) throw new Error('导出失败，请稍后重试')
    const url = URL.createObjectURL(await response.blob())
    const link = document.createElement('a')
    link.href = url
    link.download = 'template.csv'
    link.click()
    URL.revokeObjectURL(url)
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '导出失败'
  }
}

function openCreate() {
  createValues.value = Object.fromEntries(columns.map((field) => [field, '']))
  errorMessage.value = ''
  showCreate.value = true
}

async function submitCreate() {
  creating.value = true
  errorMessage.value = ''
  try {
    const response = await request(ENDPOINT, {
      method: 'POST', body: JSON.stringify(createValues.value),
    })
    const payload = await response.json()
    if (!response.ok || !payload.ok) throw new Error(payload.message || '登记失败')
    showCreate.value = false
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '登记失败'
  } finally {
    creating.value = false
  }
}

async function runAction(action: string, row: Row) {
  errorMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/${row.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ action }),
    })
    if (!response.ok) {
      throw new Error('模板市场动作未生效，请稍后重试')
    }
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '模板市场操作失败'
  }
}

async function reload() {
  errorMessage.value = ''
  const query = new URLSearchParams(filters.value as Record<string, string>).toString()
  try {
    const response = await request(`${ENDPOINT}?${query}`)
    if (!response.ok) {
      throw new Error('采集模板列表读取失败')
    }
    const payload = await response.json()
    rows.value = payload.items ?? []
    total.value = payload.total ?? rows.value.length
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '模板市场列表读取失败'
  }
}

onMounted(() => {
  void reload()
  void loadVersions()
})
</script>

<style scoped>
.version-dataset {
  margin-top: 20px;
  border-top: 2px solid var(--border);
  padding-top: 8px;
}
.identity-bar {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  align-items: flex-end;
  margin-bottom: 12px;
}
.identity-hint {
  font-size: 12px;
  color: var(--muted);
}
</style>

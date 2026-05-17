import { useEffect, useState, useRef } from 'react'
import { apiClient } from '@/api/client'
import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { Loader2, Trash2, Plus, Pencil, Check, X, Download, Upload } from 'lucide-react'

interface Project { id: number; display_name: string }
interface Dataset { id: number; project_id: number; name: string; display_name: string; description: string | null; created_at: string }
interface Document { id: string; title: string; content: string }

export default function DatasetPage() {
  const [projects, setProjects] = useState<Project[]>([])
  const [selectedProjectId, setSelectedProjectId] = useState<number | null>(null)
  const [dataset, setDataset] = useState<Dataset | null>(null)
  const [documents, setDocuments] = useState<Document[]>([])

  const [creatingDataset, setCreatingDataset] = useState(false)
  const [newDocTitle, setNewDocTitle] = useState('')
  const [newDocContent, setNewDocContent] = useState('')
  const [showAddDoc, setShowAddDoc] = useState(false)
  const [savingDoc, setSavingDoc] = useState(false)
  const [editingDocId, setEditingDocId] = useState<string | null>(null)
  const [editingContent, setEditingContent] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  // エクスポート・インポート
  const [importing, setImporting] = useState(false)
  const [importResult, setImportResult] = useState<string | null>(null)
  const importInputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    apiClient.get('/projects').then(res => setProjects(res.data))
  }, [])

  useEffect(() => {
    if (!selectedProjectId) {
      setDataset(null)
      setDocuments([])
      return
    }
    setLoading(true)
    setError(null)
    apiClient.get(`/datasets?project_id=${selectedProjectId}`)
      .then(res => {
        const list: Dataset[] = res.data
        if (list.length > 0) {
          setDataset(list[0])
          return apiClient.get(`/datasets/${list[0].id}/documents`)
        } else {
          setDataset(null)
          setDocuments([])
          return null
        }
      })
      .then(res => { if (res) setDocuments(res.data) })
      .catch(() => setError('データの読み込みに失敗しました'))
      .finally(() => setLoading(false))
  }, [selectedProjectId])

  async function createDataset() {
    if (!selectedProjectId) return
    const project = projects.find(p => p.id === selectedProjectId)
    if (!project) return
    setCreatingDataset(true)
    setError(null)
    try {
      const res = await apiClient.post('/datasets', {
        project_id: selectedProjectId,
        display_name: project.display_name,
      })
      setDataset(res.data)
      setDocuments([])
    } catch (e: any) {
      setError(e.response?.data?.detail || 'データセットの作成に失敗しました')
    } finally {
      setCreatingDataset(false)
    }
  }

  async function deleteDataset() {
    if (!dataset || !confirm(`データセット「${dataset.display_name}」を削除しますか？\nドキュメントもすべて削除されます。`)) return
    setError(null)
    try {
      await apiClient.delete(`/datasets/${dataset.id}`)
      setDataset(null)
      setDocuments([])
    } catch (e: any) {
      setError(e.response?.data?.detail || 'データセットの削除に失敗しました')
    }
  }

  async function addDocument() {
    if (!newDocContent.trim() || !dataset) return
    setError(null)
    setSavingDoc(true)
    try {
      await apiClient.post(`/datasets/${dataset.id}/documents`, {
        title: newDocTitle.trim() || undefined,
        content: newDocContent
      })
      setNewDocTitle('')
      setNewDocContent('')
      setShowAddDoc(false)
      const res = await apiClient.get(`/datasets/${dataset.id}/documents`)
      setDocuments(res.data)
    } catch (e: any) {
      setError(e.response?.data?.detail || 'エラーが発生しました')
    } finally {
      setSavingDoc(false)
    }
  }

  // 一括登録
  const [showBulkImport, setShowBulkImport] = useState(false)
  const [bulkText, setBulkText] = useState('')
  const [bulkTitlePrefix, setBulkTitlePrefix] = useState('')
  const [chunks, setChunks] = useState<string[]>([])
  const [bulkSaving, setBulkSaving] = useState(false)

  function splitIntoChunks(text: string, maxLen = 500): string[] {
    const result: string[] = []
    const paragraphs = text.split(/\n{2,}/).map(p => p.trim()).filter(Boolean)
    let current = ''
    for (const para of paragraphs) {
      if ((current + '\n\n' + para).trim().length <= maxLen) {
        current = current ? current + '\n\n' + para : para
      } else {
        if (current) result.push(current.trim())
        if (para.length > maxLen) {
          const sentences = para.split(/(?<=[。！？\n])/)
          let sub = ''
          for (const s of sentences) {
            if ((sub + s).length <= maxLen) {
              sub += s
            } else {
              if (sub) result.push(sub.trim())
              sub = s.length > maxLen ? s.slice(0, maxLen) : s
            }
          }
          if (sub) current = sub.trim()
          else current = ''
        } else {
          current = para
        }
      }
    }
    if (current.trim()) result.push(current.trim())
    return result.filter(Boolean)
  }

  async function bulkRegister() {
    if (!dataset || chunks.length === 0) return
    setBulkSaving(true)
    setError(null)
    try {
      for (let i = 0; i < chunks.length; i++) {
        const chunk = chunks[i]
        if (!chunk.trim()) continue
        const title = bulkTitlePrefix.trim()
          ? `${bulkTitlePrefix.trim()} #${i + 1}`
          : chunk.slice(0, 20).replace(/\n/g, ' ')
        await apiClient.post(`/datasets/${dataset.id}/documents`, { title, content: chunk })
      }
      const res = await apiClient.get(`/datasets/${dataset.id}/documents`)
      setDocuments(res.data)
      setShowBulkImport(false)
      setBulkText('')
      setBulkTitlePrefix('')
      setChunks([])
    } catch (e: any) {
      setError(e.response?.data?.detail || '一括登録に失敗しました')
    } finally {
      setBulkSaving(false)
    }
  }

  async function updateDocument(docId: string) {
    setError(null)
    try {
      await apiClient.put(`/datasets/${dataset!.id}/documents/${docId}`, { content: editingContent })
      setEditingDocId(null)
      const res = await apiClient.get(`/datasets/${dataset!.id}/documents`)
      setDocuments(res.data)
    } catch (e: any) {
      setError(e.response?.data?.detail || 'エラーが発生しました')
    }
  }

  async function deleteDocument(docId: string) {
    if (!dataset || !confirm('削除しますか？')) return
    await apiClient.delete(`/datasets/${dataset.id}/documents/${docId}`)
    setDocuments(d => d.filter(x => x.id !== docId))
  }

  // エクスポート（プロジェクト単位）
  async function exportDataset() {
    if (!dataset) return
    try {
      const res = await apiClient.get(`/datasets/${dataset.id}/export`, { responseType: 'blob' })
      const cd = res.headers['content-disposition'] || ''
      const match = cd.match(/filename="(.+)"/)
      const filename = match ? match[1] : `${dataset.name}.md`
      const url = URL.createObjectURL(new Blob([res.data], { type: 'text/markdown' }))
      const a = document.createElement('a')
      a.href = url
      a.download = filename
      a.click()
      URL.revokeObjectURL(url)
    } catch {
      setError('エクスポートに失敗しました')
    }
  }

  // インポート（プロジェクト単位）
  async function handleImportFile(e: React.ChangeEvent<HTMLInputElement>) {
    if (!dataset || !e.target.files?.[0]) return
    const file = e.target.files[0]
    e.target.value = ''
    setImporting(true)
    setImportResult(null)
    setError(null)
    try {
      const form = new FormData()
      form.append('file', file)
      const res = await apiClient.post(`/datasets/${dataset.id}/import`, form, {
        headers: { 'Content-Type': 'multipart/form-data' }
      })
      setImportResult(`インポート完了：${res.data.imported}件追加・更新、${res.data.skipped}件スキップ`)
      const docs = await apiClient.get(`/datasets/${dataset.id}/documents`)
      setDocuments(docs.data)
    } catch (e: any) {
      setError(e.response?.data?.detail || 'インポートに失敗しました')
    } finally {
      setImporting(false)
    }
  }

  return (
    <div className="max-w-3xl mx-auto p-6 space-y-6">

      {/* プロジェクト選択 */}
      <div>
        <Label className="text-xs text-gray-500 mb-1 block">プロジェクト</Label>
        <select
          className="w-full border rounded px-3 py-2 text-sm bg-white"
          value={selectedProjectId ?? ''}
          onChange={e => setSelectedProjectId(Number(e.target.value) || null)}
        >
          <option value="">-- 選択してください --</option>
          {projects.map(p => <option key={p.id} value={p.id}>{p.display_name}</option>)}
        </select>
      </div>

      {/* ドキュメントエリア */}
      {selectedProjectId && (
        <>
          {loading ? (
            <div className="text-sm text-gray-400">読み込み中...</div>
          ) : !dataset ? (
            <div className="border rounded p-4 bg-gray-50 space-y-3">
              <p className="text-sm text-gray-500">このプロジェクトにはデータセットがありません。</p>
              <Button size="sm" onClick={createDataset} disabled={creatingDataset}>
                <Plus className="h-3 w-3 mr-1" />{creatingDataset ? '作成中...' : 'データセットを作成'}
              </Button>
              {error && <div className="text-red-500 text-sm">{error}</div>}
            </div>
          ) : (
            <div className="space-y-4">

              {/* ヘッダー */}
              <div className="flex items-center justify-between">
                <div>
                  <span className="text-sm font-medium text-gray-700">{dataset.display_name}</span>
                  <span className="ml-2 text-xs text-gray-400">{documents.length} 件</span>
                </div>
                <div className="flex gap-2 flex-wrap justify-end">
                  <Button size="sm" variant="outline" onClick={exportDataset} title="このデータセットをエクスポート">
                    <Download className="h-3 w-3 mr-1" />エクスポート
                  </Button>
                  <Button size="sm" variant="outline" onClick={() => importInputRef.current?.click()} disabled={importing} title="MDファイルからインポート">
                    {importing ? <Loader2 className="h-3 w-3 mr-1 animate-spin" /> : <Upload className="h-3 w-3 mr-1" />}
                    インポート
                  </Button>
                  <input ref={importInputRef} type="file" accept=".md" className="hidden" onChange={handleImportFile} />
                  <Button size="sm" variant="outline" onClick={() => { setShowBulkImport(v => !v); setShowAddDoc(false); setChunks([]); setBulkText(''); setBulkTitlePrefix('') }}>
                    一括登録
                  </Button>
                  <Button size="sm" onClick={() => { setShowAddDoc(v => !v); setShowBulkImport(false); setError(null) }}>
                    <Plus className="h-3 w-3 mr-1" /> 追加
                  </Button>
                  <Button size="sm" variant="outline" onClick={deleteDataset} className="text-red-500 hover:text-red-700 hover:border-red-300">
                    <Trash2 className="h-3 w-3" />
                  </Button>
                </div>
              </div>

              {error && <div className="text-red-500 text-sm">{error}</div>}
              {importResult && (
                <div className="text-green-600 text-sm flex items-center justify-between">
                  {importResult}
                  <button onClick={() => setImportResult(null)}><X className="h-3 w-3" /></button>
                </div>
              )}

              {/* 一括登録フォーム */}
              {showBulkImport && (
                <div className="border rounded p-3 bg-gray-50 space-y-3">
                  <div className="text-xs text-gray-500 font-medium">一括登録（長文を自動分割）</div>
                  <input
                    type="text"
                    placeholder="タイトルプレフィックス（例：ホログラフィー原理）→ 「ホログラフィー原理 #1」..."
                    value={bulkTitlePrefix}
                    onChange={e => setBulkTitlePrefix(e.target.value)}
                    className="w-full border rounded px-3 py-1.5 text-sm bg-white"
                  />
                  <Textarea
                    rows={6}
                    placeholder="長文テキストを貼り付けてください"
                    value={bulkText}
                    onChange={e => { setBulkText(e.target.value); setChunks([]) }}
                    className="text-sm"
                  />
                  <div className="flex gap-2 flex-wrap">
                    <Button size="sm" variant="outline" onClick={() => setChunks(splitIntoChunks(bulkText))} disabled={!bulkText.trim()}>
                      分割プレビュー
                    </Button>
                    {chunks.length > 0 && (
                      <Button size="sm" onClick={bulkRegister} disabled={bulkSaving || chunks.some(c => c.length >= 700)}>
                        {bulkSaving ? <><Loader2 className="h-3 w-3 mr-1 animate-spin" />登録中...</> : `まとめて登録（${chunks.length}件）`}
                      </Button>
                    )}
                    <Button size="sm" variant="outline" onClick={() => { setShowBulkImport(false); setBulkText(''); setBulkTitlePrefix(''); setChunks([]) }}>キャンセル</Button>
                  </div>
                  {chunks.length > 0 && (
                    <div className="space-y-2">
                      <div className="text-xs text-gray-400">{chunks.length}件に分割されました。登録前に編集できます。</div>
                      {chunks.map((chunk, i) => (
                        <div key={i} className="space-y-1">
                          <div className="flex items-center justify-between">
                            <span className="text-xs text-gray-400">#{i + 1}</span>
                            <div className="flex items-center gap-2">
                              <span className={`text-xs ${chunk.length >= 700 ? 'text-red-500 font-medium' : chunk.length >= 500 ? 'text-yellow-600' : 'text-gray-400'}`}>
                                {chunk.length} 文字{chunk.length >= 700 ? '　要修正' : ''}
                              </span>
                              <button onClick={() => setChunks(prev => prev.filter((_, j) => j !== i))} className="text-gray-300 hover:text-red-400">
                                <X className="h-3 w-3" />
                              </button>
                            </div>
                          </div>
                          <Textarea
                            rows={6}
                            value={chunk}
                            onChange={e => setChunks(prev => prev.map((c, j) => j === i ? e.target.value : c))}
                            className={`text-sm ${chunk.length >= 700 ? 'border-red-400' : chunk.length >= 500 ? 'border-yellow-400' : ''}`}
                          />
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}

              {/* ドキュメント追加フォーム */}
              {showAddDoc && (
                <div className="border rounded p-3 bg-gray-50 space-y-2">
                  <input
                    type="text"
                    placeholder="タイトル（任意・検索対象外）"
                    value={newDocTitle}
                    onChange={e => setNewDocTitle(e.target.value)}
                    className="w-full border rounded px-3 py-1.5 text-sm bg-white"
                  />
                  <Textarea
                    rows={4}
                    placeholder="本文（検索対象）"
                    value={newDocContent}
                    onChange={e => setNewDocContent(e.target.value)}
                    className={`text-sm ${newDocContent.length >= 700 ? 'border-red-400' : newDocContent.length >= 500 ? 'border-yellow-400' : ''}`}
                  />
                  <div className={`text-xs text-right ${newDocContent.length >= 700 ? 'text-red-500 font-medium' : newDocContent.length >= 500 ? 'text-yellow-600' : 'text-gray-400'}`}>
                    {newDocContent.length} 文字
                    {newDocContent.length >= 700 && '　700文字以上は登録できません'}
                    {newDocContent.length >= 500 && newDocContent.length < 700 && '　500文字を超えています（推奨：500文字以内）'}
                  </div>
                  <div className="flex gap-2">
                    <Button size="sm" onClick={addDocument} disabled={savingDoc || newDocContent.length >= 700}>
                      {savingDoc ? <><Loader2 className="h-3 w-3 mr-1 animate-spin" />登録中...</> : '登録'}
                    </Button>
                    <Button size="sm" variant="outline" onClick={() => { setShowAddDoc(false); setNewDocTitle(''); setNewDocContent('') }}>キャンセル</Button>
                  </div>
                </div>
              )}

              {/* ドキュメント一覧 */}
              <div className="space-y-2">
                {documents.length === 0 ? (
                  <div className="text-sm text-gray-400 text-center py-8">ドキュメントがありません</div>
                ) : (
                  documents.map(doc => (
                    <div key={doc.id} className="border rounded p-3 bg-white">
                      {editingDocId === doc.id ? (
                        <div className="space-y-2">
                          <Textarea
                            rows={4}
                            value={editingContent}
                            onChange={e => setEditingContent(e.target.value)}
                            className="text-sm font-mono"
                          />
                          <div className="flex gap-2">
                            <Button size="sm" onClick={() => updateDocument(doc.id)}><Check className="h-3 w-3 mr-1" />保存</Button>
                            <Button size="sm" variant="outline" onClick={() => setEditingDocId(null)}><X className="h-3 w-3 mr-1" />キャンセル</Button>
                          </div>
                        </div>
                      ) : (
                        <div className="flex items-start justify-between gap-2">
                          <div className="flex-1 min-w-0">
                            {doc.title && (
                              <div className="text-xs font-medium text-gray-500 mb-1">{doc.title}</div>
                            )}
                            <p className="text-sm text-gray-800 whitespace-pre-wrap break-all">{doc.content}</p>
                          </div>
                          <div className="flex gap-1 shrink-0">
                            <button onClick={() => { setEditingDocId(doc.id); setEditingContent(doc.content) }} className="text-gray-400 hover:text-blue-500">
                              <Pencil className="h-3 w-3" />
                            </button>
                            <button onClick={() => deleteDocument(doc.id)} className="text-gray-400 hover:text-red-500">
                              <Trash2 className="h-3 w-3" />
                            </button>
                          </div>
                        </div>
                      )}
                    </div>
                  ))
                )}
              </div>

            </div>
          )}
        </>
      )}

    </div>
  )
}

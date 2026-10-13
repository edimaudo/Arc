/* Arc browser-local persistence for analyses, discovery results, insights, and preferences. */
(() => {
  const DB_NAME = 'arc-workspace';
  const DB_VERSION = 2;
  let connection;

  function open() {
    if (connection) return connection;
    connection = new Promise((resolve, reject) => {
      if (!('indexedDB' in window)) {
        reject(new Error('Browser saving is unavailable. Try a current version of Chrome, Firefox, Safari, or Edge.'));
        return;
      }
      const request = indexedDB.open(DB_NAME, DB_VERSION);
      request.onupgradeneeded = () => {
        const db = request.result;
        if (!db.objectStoreNames.contains('analyses')) db.createObjectStore('analyses', { keyPath: 'analysis_id' });
        if (!db.objectStoreNames.contains('discoveries')) db.createObjectStore('discoveries', { keyPath: 'id' });
        if (!db.objectStoreNames.contains('preferences')) db.createObjectStore('preferences', { keyPath: 'key' });
        if (!db.objectStoreNames.contains('insights')) db.createObjectStore('insights', { keyPath: 'id' });
      };
      request.onsuccess = () => resolve(request.result);
      request.onerror = () => reject(request.error || new Error('Could not open browser storage.'));
      request.onblocked = () => reject(new Error('Arc storage upgrade is blocked by another open tab. Close other Arc tabs and reload.'));
    });
    return connection;
  }

  async function request(storeName, mode, action) {
    const db = await open();
    return new Promise((resolve, reject) => {
      const tx = db.transaction(storeName, mode);
      const req = action(tx.objectStore(storeName));
      req.onsuccess = () => resolve(req.result);
      req.onerror = () => reject(req.error || new Error('Browser storage operation failed.'));
      tx.onabort = () => reject(tx.error || new Error('Browser storage transaction failed.'));
    });
  }

  window.ArcStore = {
    open,
    getAnalysis: id => request('analyses', 'readonly', s => s.get(id)),
    putAnalysis: analysis => request('analyses', 'readwrite', s => s.put(analysis)),
    deleteAnalysis: id => request('analyses', 'readwrite', s => s.delete(id)),
    allAnalyses: async () => (await request('analyses', 'readonly', s => s.getAll())).sort((a, b) => (b.updated_at || b.created_at || '').localeCompare(a.updated_at || a.created_at || '')),
    putDiscovery: discovery => request('discoveries', 'readwrite', s => s.put(discovery)),
    allDiscoveries: async () => (await request('discoveries', 'readonly', s => s.getAll())).sort((a, b) => (b.created_at || '').localeCompare(a.created_at || '')),
    putInsight: insight => request('insights', 'readwrite', s => s.put(insight)),
    allInsights: async () => (await request('insights', 'readonly', s => s.getAll())).sort((a, b) => (b.created_at || '').localeCompare(a.created_at || '')),
    getPreference: async key => { const row = await request('preferences', 'readonly', s => s.get(key)); return row ? row.value : undefined; },
    setPreference: row => request('preferences', 'readwrite', s => s.put(row)),
  };
})();

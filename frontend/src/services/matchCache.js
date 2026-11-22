const entries = new Map()
const inflight = new Map()
const viewState = {
  jobId: null,
  activeId: null,
  userPicked: false,
}
const pageData = {
  jobs: null,
  candidates: null,
  documents: null,
  docsState: 'loading',
}

export function getMatchEntry(key) {
  return entries.get(key) || null
}

export function setMatchEntry(key, value) {
  if (value == null) entries.delete(key)
  else entries.set(key, value)
}

export function getInflightMatch(key) {
  return inflight.get(key) || null
}

export function setInflightMatch(key, promise) {
  if (promise == null) inflight.delete(key)
  else inflight.set(key, promise)
}

export function clearMatchEntries() {
  entries.clear()
  inflight.clear()
}

export function getMatchViewState() {
  return { ...viewState }
}

export function setMatchViewState(next) {
  Object.assign(viewState, next)
}

export function getMatchPageData() {
  return {
    jobs: pageData.jobs,
    candidates: pageData.candidates,
    documents: pageData.documents,
    docsState: pageData.docsState,
  }
}

export function setMatchPageData(next) {
  Object.assign(pageData, next)
}

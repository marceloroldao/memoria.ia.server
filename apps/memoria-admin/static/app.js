const $ = (id) => document.getElementById(id);

function headers() {
  return {
    'Content-Type': 'application/json',
    'X-Memoria-Key': $('apiKey').value,
  };
}

function scope() {
  const applicationId = $('applicationId').value.trim();
  return { application_id: applicationId || null };
}

function memoryKeys() {
  return $('memoryKeys').value.split(',').map(v => v.trim()).filter(Boolean);
}

function baselineContext() {
  return $('baselineContext').value.split('\n').map(v => v.trim()).filter(Boolean);
}

function csv(id) {
  return $(id).value.split(',').map(v => v.trim()).filter(Boolean);
}

async function api(path, options = {}) {
  const response = await fetch(path, { ...options, headers: { ...headers(), ...(options.headers || {}) } });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(body.detail || `${response.status} ${response.statusText}`);
  return body;
}

function showMetrics(metrics, prefix = '') {
  const target = $('metrics');
  target.innerHTML = '';
  if (!metrics) return;
  const entries = Object.entries(metrics);
  for (const [key, value] of entries) {
    const div = document.createElement('div');
    div.className = 'metric';
    const strong = document.createElement('strong');
    strong.textContent = value === null ? 'n/a' : String(value);
    const span = document.createElement('span');
    span.textContent = `${prefix}${key}`;
    div.append(strong, span);
    target.appendChild(div);
  }
}

async function refreshConfiguration() {
  try {
    const body = await api('/api/v1/admin/configuration');
    $('llmConfigStatus').textContent = JSON.stringify(body.llm, null, 2);
    $('licenseConfigStatus').textContent = JSON.stringify(body.license, null, 2);
    if (body.llm && body.llm.provider) $('llmProvider').value = body.llm.provider;
    if (body.llm && body.llm.model) $('llmModel').value = body.llm.model;
    if (body.license) {
      $('licenseId').value = body.license.license_id || '';
      $('licensePlan').value = body.license.plan || 'early_access';
      $('licenseValidUntil').value = body.license.valid_until || '';
      $('licenseMaxNodes').value = body.license.max_nodes || 1;
      $('licenseCapabilities').value = (body.license.capabilities || []).join(',');
    }
  } catch (err) {
    $('llmConfigStatus').textContent = `Error: ${err.message}`;
    $('licenseConfigStatus').textContent = `Error: ${err.message}`;
  }
}

async function refreshApplications() {
  try {
    const body = await api('/api/v1/admin/applications');
    $('applications').textContent = JSON.stringify(body.applications, null, 2);
  } catch (err) {
    $('applications').textContent = `Error: ${err.message}`;
  }
}

$('refreshAdmin').addEventListener('click', async () => {
  try {
    const body = await api('/api/v1/admin/status');
    $('admin').textContent = JSON.stringify(body, null, 2);
    await Promise.all([refreshApplications(), refreshConfiguration()]);
  } catch (err) {
    $('admin').textContent = `Error: ${err.message}`;
  }
});

$('refreshApplications').addEventListener('click', refreshApplications);
$('refreshConfiguration').addEventListener('click', refreshConfiguration);

$('saveLlmConfig').addEventListener('click', async () => {
  $('llmConfigStatus').textContent = 'Saving...';
  try {
    const apiKey = $('llmApiKey').value.trim();
    const payload = {
      provider: $('llmProvider').value,
      model: $('llmModel').value.trim(),
    };
    if (apiKey) payload.api_key = apiKey;
    const body = await api('/api/v1/admin/configuration/llm', {
      method: 'PUT',
      body: JSON.stringify(payload),
    });
    $('llmApiKey').value = '';
    $('llmConfigStatus').textContent = JSON.stringify({
      ...body.llm,
      restart_required: body.restart_required,
    }, null, 2);
  } catch (err) {
    $('llmConfigStatus').textContent = `Error: ${err.message}`;
  }
});

$('saveLicenseConfig').addEventListener('click', async () => {
  $('licenseConfigStatus').textContent = 'Saving...';
  try {
    const body = await api('/api/v1/admin/configuration/license', {
      method: 'PUT',
      body: JSON.stringify({
        license_id: $('licenseId').value.trim(),
        plan: $('licensePlan').value.trim() || 'early_access',
        valid_until: $('licenseValidUntil').value.trim() || null,
        max_nodes: Number($('licenseMaxNodes').value || 1),
        capabilities: csv('licenseCapabilities'),
      }),
    });
    $('licenseConfigStatus').textContent = JSON.stringify(body, null, 2);
  } catch (err) {
    $('licenseConfigStatus').textContent = `Error: ${err.message}`;
  }
});

$('createApplication').addEventListener('click', async () => {
  $('newCredential').textContent = 'Creating...';
  try {
    const scopes = csv('newApplicationScopes');
    const body = await api('/api/v1/admin/applications', {
      method: 'POST',
      body: JSON.stringify({
        application_id: $('newApplicationId').value.trim(),
        display_name: $('newApplicationName').value.trim() || null,
        scopes,
      }),
    });
    $('newCredential').textContent = [
      'SAVE THIS CREDENTIAL NOW. IT WILL NOT BE SHOWN AGAIN.',
      '',
      body.credential,
      '',
      `Application: ${body.application.application_id}`,
      `Scopes: ${body.application.scopes.join(', ')}`,
    ].join('\n');
    await refreshApplications();
  } catch (err) {
    $('newCredential').textContent = `Error: ${err.message}`;
  }
});

$('sendMemoria').addEventListener('click', async () => {
  $('answer').textContent = 'Sending...';
  try {
    const body = await api('/api/v1/chat', {
      method: 'POST',
      body: JSON.stringify({
        message: $('message').value,
        mode: 'memoria',
        memory_keys: memoryKeys(),
        scope: scope(),
      }),
    });
    $('answer').textContent = body.text;
    showMetrics(body.metrics);
  } catch (err) {
    $('answer').textContent = `Error: ${err.message}`;
  }
});

$('compare').addEventListener('click', async () => {
  $('answer').textContent = 'Comparing...';
  try {
    const body = await api('/api/v1/chat/compare', {
      method: 'POST',
      body: JSON.stringify({
        message: $('message').value,
        baseline_context: baselineContext(),
        memory_keys: memoryKeys(),
        scope: scope(),
      }),
    });
    $('answer').textContent = JSON.stringify({
      baseline: body.baseline.text,
      memoria: body.memoria.text,
      token_reduction_percent: body.token_reduction_percent,
    }, null, 2);
    showMetrics({
      baseline_input_tokens: body.baseline.metrics.input_tokens,
      memoria_input_tokens: body.memoria.metrics.input_tokens,
      token_reduction_percent: body.token_reduction_percent,
      memory_hits: body.memoria.metrics.memory_hits,
      memory_misses: body.memoria.metrics.memory_misses,
      memory_latency_ms: body.memoria.metrics.memory_latency_ms,
      llm_latency_ms: body.memoria.metrics.llm_latency_ms,
      provider: body.memoria.metrics.provider,
      model: body.memoria.metrics.model,
    });
  } catch (err) {
    $('answer').textContent = `Error: ${err.message}`;
  }
});

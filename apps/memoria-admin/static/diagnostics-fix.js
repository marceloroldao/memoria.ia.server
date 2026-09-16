(() => {
  const button = document.getElementById('downloadReport');
  const status = document.getElementById('diagnosticStatus');
  if (!button || !status) return;

  const download = (text) => {
    const blob = new Blob([text], {type:'text/plain;charset=utf-8'});
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `memoria-growth-report-${new Date().toISOString().replace(/[:.]/g,'-')}.txt`;
    document.body.appendChild(a); a.click(); a.remove(); URL.revokeObjectURL(url);
  };

  button.hidden = false;
  button.style.display = '';
  button.textContent = 'Baixar relatório TXT';
  button.onclick = async () => {
    button.disabled = true;
    const old = button.textContent;
    button.textContent = 'Gerando relatório…';
    try {
      const response = await fetch('/api/server/v1/growth-diagnostics', {headers:{'Accept':'application/json'}});
      const body = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(body.detail || body.error || `${response.status} ${response.statusText}`);
      const text = [
        'MEMORIA.IA SERVER - GROWTH DIAGNOSTICS',
        `Gerado em: ${new Date().toISOString()}`,
        '',
        JSON.stringify(body, null, 2)
      ].join('\n');
      status.textContent = text.length > 30000 ? `${text.slice(0,30000)}\n\n[visualização limitada a 30000 caracteres; o TXT baixado contém o relatório completo]` : text;
      status.scrollTop = 0;
      download(text);
    } catch (error) {
      status.textContent = `Falha ao gerar relatório: ${error.message}`;
    } finally {
      button.disabled = false;
      button.textContent = old;
    }
  };
})();

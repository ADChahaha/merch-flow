// Offline ACP peer: exercise real pipes without an API key or external website.
const fs = require('node:fs');
const readline = require('node:readline');
const path = require('node:path');
const sample = '中文・日本語・缶バッジ 🛍️';
let cwd;
const send = (message) => process.stdout.write(JSON.stringify(message) + '\n');
const update = (value) => send({jsonrpc: '2.0', method: 'session/update', params: {update: value}});
readline.createInterface({input: process.stdin}).on('line', (line) => {
  const request = JSON.parse(line);
  const reply = (result) => send({jsonrpc: '2.0', id: request.id, result});
  if (request.method === 'initialize') return reply({protocolVersion: 1});
  if (request.method === 'session/new') {
    cwd = request.params.cwd;
    return reply({sessionId: 'encoding-regression-session'});
  }
  if (request.method === 'session/prompt') {
    if (!request.params.prompt[0].text.includes(sample)) {
      return send({id: request.id, error: 'Unicode prompt was corrupted'});
    }
    update({sessionUpdate: 'tool_call', title: 'read', status: 'in_progress'});
    update({sessionUpdate: 'tool_call_update', status: 'completed'});
    process.stderr.write('诊断：' + sample + '\n');
    fs.writeFileSync(path.join(cwd, 'products.json'), JSON.stringify({
      title: sample,
      products: [{name: sample, price: 550, price_text: '550円（税込）',
        detail: '测试（全角括号）', source_url: 'https://example.com/product'}]
    }), 'utf8');
    update({sessionUpdate: 'agent_message_chunk', content: {type: 'text', text: sample}});
    return reply({stopReason: 'end_turn'});
  }
});

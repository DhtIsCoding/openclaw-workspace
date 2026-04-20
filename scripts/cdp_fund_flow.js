#!/usr/bin/env node
/**
 * CDP 东财资金流采集器
 * 通过 MostLogin 浏览器（端口 50840）控制真实浏览器渲染页面
 * 优点：WAF 无法封禁（真实浏览器流量），返回完整字段
 */

const WebSocket = require('/home/dht/.local/share/fnm/node-versions/v24.14.1/installation/lib/node_modules/openclaw/node_modules/ws');
const path = require('path');

const CDP_HOST = '127.0.0.1:50840';
// 使用 MostLogin 的主页面
const PAGES = [
  '54844AF5D3ED67079F6740209D5B2F5F', // MostLogin main page
  '8016C2779AB62FEE410519AE519AE954', // Test console page
];

// 简单 CDP 包装类
class CDPClient {
  constructor(wsUrl) {
    this.ws = new WebSocket(wsUrl);
    this.id = 1;
    this.pending = {};
    this._resolve = null;
    this._ready = new Promise(resolve => { this._resolve = resolve; });
  }

  onMessage(msg) {}

  send(obj) {
    return new Promise(resolve => {
      if (obj.id === undefined) obj.id = this.id++;
      this.pending[obj.id] = resolve;
      this.ws.send(JSON.stringify(obj));
    });
  }

  async eval(expression) {
    const r = await this.send({method: 'Runtime.evaluate', params: {expression, returnByValue: true}});
    return r.result && r.result.result && r.result.result.value;
  }

  async navigate(url) {
    await this.send({method: 'Page.navigate', params: {url}});
    // 等待页面加载
    await new Promise(r => setTimeout(r, 8000));
  }
}

// 主采集函数
async function getStockFundFlow(stockCode) {
  // 确定市场前缀
  const prefix = stockCode.startsWith('6') || stockCode.startsWith('5') ? 'sh' : 'sz';
  const url = `https://data.eastmoney.com/zjlx/${stockCode}.html`;
  const fullCode = `${prefix}${stockCode}`;
  
  const wsUrl = `ws://${CDP_HOST}/devtools/page/${PAGES[0]}`;
  const client = new CDPClient(wsUrl);
  
  await new Promise(r => {
    client.ws.on('open', () => r());
    client.ws.on('message', data => {
      const msg = JSON.parse(data.toString());
      if (msg.id && client.pending[msg.id]) {
        client.pending[msg.id](msg);
        delete client.pending[msg.id];
      }
      client.onMessage(msg);
    });
  });
  
  // 启用必要的 Domain
  await client.send({method: 'Page.enable'});
  await client.send({method: 'Runtime.enable'});
  
  // 导航
  await client.navigate(url);
  
  // 提取资金流数据
  const script = `
    (function() {
      var result = {code: '${fullCode}', url: window.location.href};
      var text = document.body.innerText;
      
      // 提取关键数字
      var re = /([+-]?\\d+\\.?\\d*)(亿|万|万手)/g;
      var nums = [];
      var m;
      while ((m = re.exec(text)) !== null) {
        nums.push(m[0]);
      }
      result.numbers = nums.slice(0, 30);
      
      // 提取表格行数据（资金流向排名表格）
      var rows = [];
      var tables = document.querySelectorAll('.dataTables_wrapper table, #tableWrap table, table');
      tables.forEach(function(tbl) {
        var headers = [];
        tbl.querySelectorAll('thead th, .head th').forEach(function(h) {
          headers.push(h.innerText.trim());
        });
        tbl.querySelectorAll('tbody tr').forEach(function(row, i) {
          if (i >= 20) return;
          var cells = row.querySelectorAll('td');
          if (cells.length >= 3) {
            var rowData = {};
            headers.forEach(function(h, j) {
              rowData[h] = cells[j] ? cells[j].innerText.trim() : '';
            });
            rows.push(rowData);
          }
        });
      });
      result.tableRows = rows;
      
      return JSON.stringify(result);
    })()
  `;
  
  const raw = await client.eval(script);
  let data;
  try { data = JSON.parse(raw); } catch(e) { data = {raw}; }
  
  client.ws.terminate();
  return data;
}

// 命令行入口
const stockCode = process.argv[2];
if (!stockCode) {
  console.error('Usage: node cdp_fund_flow.js <stockCode>');
  process.exit(1);
}

getStockFundFlow(stockCode).then(data => {
  console.log(JSON.stringify(data, null, 2));
}).catch(e => {
  console.error('Error:', e.message);
  process.exit(1);
});

// 测试
if (require.main === module && process.argv[2] === '--test') {
  getStockFundFlow('600879').then(data => {
    console.log(JSON.stringify(data, null, 2));
  });
}

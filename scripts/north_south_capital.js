#!/usr/bin/env node
/**
 * north_south_capital.js — 沪深港通资金流向采集
 * 通过 Playwright (Node.js) 访问 EastMoney 沪深港通页面
 */
const { chromium } = require('/home/dht/.local/share/fnm/node-versions/v24.14.1/installation/lib/node_modules/playwright');
const path = require('path');

const DB_PATH = path.join(__dirname, '..', 'data', 'daily_close.db');

function parseAmount(text) {
    if (!text || text === '--' || text === '-') return null;
    const m = text.match(/([-\d.]+)/);
    if (!m) return null;
    let val = parseFloat(m[1]);
    if (text.includes('万')) val /= 10000;
    return val;
}

function extractBetween(text, startMarker, endMarker, fallback) {
    // 在 startMarker 之后、endMarker 之前的内容中查找数字
    const idx = text.indexOf(startMarker);
    if (idx < 0) return fallback;
    const chunk = text.substring(idx, Math.min(idx + 500, text.length));
    const endIdx = chunk.indexOf(endMarker);
    const target = endIdx > 0 ? chunk.substring(0, endIdx) : chunk;
    const m = target.match(/([-\d.]+)/);
    return m ? parseFloat(m[1]) : fallback;
}

async function main() {
    console.log('[北向/南向资金] 开始采集...');
    
    const browser = await chromium.launch({ headless: true, args: ['--no-sandbox'] });
    const page = await browser.newPage();
    
    await page.goto('https://data.eastmoney.com/hsgtcg/', 
        { waitUntil: 'domcontentloaded', timeout: 20000 });
    // 等待JS渲染完成（8秒足够）
    await page.waitForTimeout(8000);
    
    const text = await page.evaluate(() => document.body.innerText);
    await browser.close();
    
    // 提取日期
    let dateMatch = text.match(/数据日期[：:]\s*(\d{4}-\d{2}-\d{2})/);
    const tradeDate = dateMatch ? dateMatch[1] : new Date().toISOString().slice(0, 10);
    
    // ===== 北向资金（沪股通） =====
    // 找到"沪股通"section，然后找"成交总额"和"领涨股"
    const hgtIdx = text.indexOf('沪股通\n成交总额');
    let hgtTotal = null, hgtLeader = null;
    if (hgtIdx >= 0) {
        const chunk = text.substring(hgtIdx, hgtIdx + 100);
        const m = chunk.match(/成交总额\s*([-\d.]+)亿/);
        hgtTotal = m ? parseFloat(m[1]) : null;
        const lm = chunk.match(/领涨股\s*(\S+)/);
        hgtLeader = lm ? lm[1] : null;
    }
    
    // ===== 北向资金（深股通） =====
    const sgtIdx = text.indexOf('深股通\n成交总额');
    let sgtTotal = null, sgtLeader = null;
    if (sgtIdx >= 0) {
        const chunk = text.substring(sgtIdx, sgtIdx + 100);
        const m = chunk.match(/成交总额\s*([-\d.]+)亿/);
        sgtTotal = m ? parseFloat(m[1]) : null;
        const lm = chunk.match(/领涨股\s*(\S+)/);
        sgtLeader = lm ? lm[1] : null;
    }
    
    // ===== 北向合计 =====
    const northTotalMatch = text.match(/北向资金\n成交总额\s*([-\d.]+)亿/);
    const northTotal = northTotalMatch ? parseFloat(northTotalMatch[1]) : null;
    
    // ===== 南向资金（港股通沪） =====
    const southHgtIdx = text.indexOf('港股通(沪)\n净买额');
    let southHgtNet = null, southHgtBuy = null, southHgtSell = null;
    if (southHgtIdx >= 0) {
        const chunk = text.substring(southHgtIdx, southHgtIdx + 200);
        const m1 = chunk.match(/净买额\s*([-\d.]+)亿/);
        const m2 = chunk.match(/买入额\s*([-\d.]+)亿/);
        const m3 = chunk.match(/卖出额\s*([-\d.]+)亿/);
        southHgtNet = m1 ? parseFloat(m1[1]) : null;
        southHgtBuy = m2 ? parseFloat(m2[1]) : null;
        southHgtSell = m3 ? parseFloat(m3[1]) : null;
    }
    
    // ===== 南向资金（港股通深） =====
    const southSgtIdx = text.indexOf('港股通(深)\n净买额');
    let southSgtNet = null, southSgtBuy = null, southSgtSell = null;
    if (southSgtIdx >= 0) {
        const chunk = text.substring(southSgtIdx, southSgtIdx + 200);
        const m1 = chunk.match(/净买额\s*([-\d.]+)亿/);
        const m2 = chunk.match(/买入额\s*([-\d.]+)亿/);
        const m3 = chunk.match(/卖出额\s*([-\d.]+)亿/);
        southSgtNet = m1 ? parseFloat(m1[1]) : null;
        southSgtBuy = m2 ? parseFloat(m2[1]) : null;
        southSgtSell = m3 ? parseFloat(m3[1]) : null;
    }
    
    // ===== 南向合计 =====
    const southTotalNetMatch = text.match(/南向资金\n净买额\s*([-\d.]+)亿/);
    const southTotalNet = southTotalNetMatch ? parseFloat(southTotalNetMatch[1]) : null;
    
    console.log(`数据日期: ${tradeDate}`);
    console.log(`北向资金:`);
    console.log(`  沪股通成交总额: ${hgtTotal}亿元  领涨股: ${hgtLeader}`);
    console.log(`  深股通成交总额: ${sgtTotal}亿元  领涨股: ${sgtLeader}`);
    console.log(`  北向合计: ${northTotal}亿元`);
    console.log(`南向资金:`);
    console.log(`  港股通(沪)净买额: ${southHgtNet}亿  买入:${southHgtBuy}亿 卖出:${southHgtSell}亿`);
    console.log(`  港股通(深)净买额: ${southSgtNet}亿  买入:${southSgtBuy}亿 卖出:${southSgtSell}亿`);
    console.log(`  南向合计净买额: ${southTotalNet}亿`);
    
    // 保存到数据库（通过Python脚本）
    const { execSync } = require('child_process');
    const saveData = {
        tradeDate,
        records: [
            { direction: 'north_hgt', total: hgtTotal, leader: hgtLeader },
            { direction: 'north_sgt', total: sgtTotal, leader: sgtLeader },
            { direction: 'north_total', total: northTotal },
            { direction: 'south_hgt', net: southHgtNet, buy: southHgtBuy, sell: southHgtSell },
            { direction: 'south_sgt', net: southSgtNet, buy: southSgtBuy, sell: southSgtSell },
        ]
    };
    const saveScript = path.join(__dirname, 'save_capital.py');
    try {
        const result = execSync(`python3 "${saveScript}" '${JSON.stringify(saveData)}'`, { encoding: 'utf8' });
        console.log(result.trim());
    } catch(e) {
        console.log('DB save warning:', e.message);
    }
    
    console.log('[完成]');
    return { tradeDate, hgtTotal, sgtTotal, northTotal, southHgtNet, southSgtNet, southTotalNet };
}

main().catch(e => {
    console.error('[错误]', e.message);
    process.exit(1);
});

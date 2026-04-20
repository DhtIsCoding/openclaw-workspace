const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');
const { execSync } = require('child_process');

const WORKDIR = '/home/dht/.openclaw/workspace/knowledge/stocks/日本蜡烛图技术/';
const CDP_URL = 'http://localhost:50840';

async function sleep(ms) {
  return new Promise(r => setTimeout(r, ms));
}

async function getClipboardText() {
  try {
    const result = execSync(
      '/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe -Command "Get-Clipboard"',
      { encoding: 'utf8', timeout: 5000 }
    );
    return result.trim();
  } catch (e) {
    return '';
  }
}

async function tryExtractTextFromPage(page) {
  // Try to find text content directly in the DOM
  // weread pages have various possible text containers
  const text = await page.evaluate(() => {
    // Try various selectors that might contain book text
    const candidates = document.querySelectorAll('*');
    let bestText = '';
    
    // Common patterns for reader text content
    const selectors = [
      '.reader_page_content',
      '.page_content', 
      '.reader_content',
      '.weread-reader-content',
      '[class*="reader"]',
      '[class*="content"]'
    ];
    
    for (const sel of selectors) {
      const el = document.querySelector(sel);
      if (el && el.innerText && el.innerText.length > 100) {
        return el.innerText.trim();
      }
    }
    
    // If no selector matches, try body
    return document.body.innerText.substring(0, 5000);
  });
  
  if (text && text.length > 50) {
    return text;
  }
  return null;
}

async function selectAndExtractText(page, yStart, yEnd) {
  // Move to starting position
  await page.mouse.move(587, yStart);
  await page.mouse.down();
  
  // Drag slowly to ending position
  const steps = Math.max(6, Math.floor((yEnd - yStart) / 8));
  for (let i = 0; i <= steps; i++) {
    const y = yStart + (yEnd - yStart) * (i / steps);
    await page.mouse.move(587, y);
    await page.waitForTimeout(8);
  }
  
  await page.mouse.up();
  await page.waitForTimeout(700);
  
  // Ctrl+C
  await page.keyboard.press('Control+c');
  await page.waitForTimeout(300);
  
  return await getClipboardText();
}

async function main() {
  console.log('Connecting to Chrome CDP...');
  const browser = await chromium.connectOverCDP(CDP_URL);
  const context = browser.contexts()[0];
  const pages = context.pages();
  const wrPage = pages.find(p => p.url().includes('weread.qq.com'));

  if (!wrPage) {
    console.error('weread.qq.com page not found!');
    console.log('Available pages:', pages.map(p => p.url()));
    await browser.close();
    return;
  }

  console.log('Found weread page:', wrPage.url());
  await sleep(1000);

  // Determine starting page
  let existingFiles = fs.readdirSync(WORKDIR).filter(f => f.startsWith('text_') && f.endsWith('.txt'));
  let maxNum = 0;
  for (const f of existingFiles) {
    const m = f.match(/text_(\d+)\.txt/);
    if (m) maxNum = Math.max(maxNum, parseInt(m[1]));
  }
  
  let currentPage = maxNum + 1;
  if (maxNum > 0) {
    console.log(`text_001.txt to text_${String(maxNum).padStart(3, '0')}.txt already exist. Starting from page ${currentPage}`);
  } else {
    currentPage = 2; // Start from page 2 if only text_001 doesn't exist or is the only one
    console.log('No existing text files. Starting from page 2');
  }

  let emptyPagesCount = 0;
  let totalChars = 0;
  let completedPages = 0;

  while (currentPage <= 250) {
    const pageNum = String(currentPage).padStart(3, '0');
    const screenshotPath = `${WORKDIR}page_${pageNum}.png`;
    const textPath = `${WORKDIR}text_${pageNum}.txt`;

    console.log(`\n=== Page ${currentPage} (${pageNum}) ===`);

    // Check if text already extracted
    if (fs.existsSync(textPath)) {
      console.log('Text file exists, skipping...');
      currentPage++;
      continue;
    }

    // Click next page button if not on first page
    if (currentPage > 1) {
      const nextBtn = await wrPage.$('.renderTarget_pager_button_right');
      if (nextBtn) {
        await nextBtn.click();
        await sleep(2500);
      } else {
        console.log('Next button not found, trying to find it differently...');
        // Try clicking by evaluating the button
        const clicked = await wrPage.evaluate(() => {
          const btn = document.querySelector('.renderTarget_pager_button_right');
          if (btn) { btn.click(); return true; }
          return false;
        });
        if (!clicked) {
          console.log('Could not click next button, stopping');
          break;
        }
        await sleep(2500);
      }
    }

    // Screenshot
    await wrPage.screenshot({ path: screenshotPath });
    console.log('Screenshot saved:', screenshotPath);

    // Try to extract text from DOM first
    let text = await tryExtractTextFromPage(wrPage);
    
    if (!text || text.length < 30) {
      console.log('DOM extraction gave < 30 chars, using image-based extraction...');
      // For now, save a placeholder and note we need image analysis
      // Actually let's try OCR with tesseract
      try {
        const ocrResult = execSync(`tesseract "${screenshotPath}" stdout -l chi_sim --psm 6 2>/dev/null`, 
          { encoding: 'utf8', timeout: 15000 });
        text = ocrResult.trim();
        console.log('OCR result length:', text.length);
      } catch (e) {
        console.log('OCR failed:', e.message);
        text = '';
      }
    }

    if (text && text.length >= 30) {
      fs.writeFileSync(textPath, text, 'utf8');
      totalChars += text.length;
      completedPages++;
      console.log(`Saved ${text.length} chars to ${textPath}`);
      emptyPagesCount = 0;
    } else {
      // Text too short or empty
      if (text && text.length > 0) {
        fs.writeFileSync(textPath, text, 'utf8');
        console.log(`Short text (${text.length} chars) saved to ${textPath}`);
        totalChars += text.length;
        completedPages++;
      }
      
      emptyPagesCount++;
      console.log(`Page ${currentPage} has < 30 chars (${text?.length || 0}), empty count: ${emptyPagesCount}`);
      
      if (emptyPagesCount >= 2) {
        console.log('Two consecutive pages with < 30 chars, stopping');
        break;
      }
    }

    currentPage++;
  }

  console.log(`\n=== Summary ===`);
  console.log(`Pages processed: ${completedPages}`);
  console.log(`Total characters: ${totalChars}`);
  
  // Merge all text files
  console.log('\nMerging all text files...');
  const allTextFiles = fs.readdirSync(WORKDIR)
    .filter(f => f.startsWith('text_') && f.endsWith('.txt'))
    .sort((a, b) => {
      const numA = parseInt(a.match(/text_(\d+)\.txt/)[1]);
      const numB = parseInt(b.match(/text_(\d+)\.txt/)[1]);
      return numA - numB;
    });
  
  let mergedText = '';
  for (const f of allTextFiles) {
    const content = fs.readFileSync(path.join(WORKDIR, f), 'utf8');
    mergedText += `\n\n=== ${f} ===\n\n${content}`;
  }
  
  fs.writeFileSync(`${WORKDIR}日本蜡烛图技术_全文.txt`, mergedText, 'utf8');
  console.log(`Merged ${allTextFiles.length} files to 日本蜡烛图技术_全文.txt`);
  
  await browser.close();
  console.log('Done!');
}

main().catch(console.error);

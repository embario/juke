#!/usr/bin/env node
const fs = require('fs/promises');
const path = require('path');
const sharp = require('sharp');

async function ensureDir(dirPath) {
  await fs.mkdir(dirPath, { recursive: true });
}

function parseSize(size) {
  if (typeof size === 'number') {
    return { width: size, height: size };
  }
  if (typeof size !== 'string') {
    throw new Error(`Unsupported size value: ${size}`);
  }
  const [width, height] = size.split(/[:x]/i).map(Number);
  if (!Number.isFinite(width) || !Number.isFinite(height)) {
    throw new Error(`Invalid size string: ${size}`);
  }
  return { width, height };
}

async function renderJob(job, rootDir) {
  const cache = new Map();
  for (const inputRel of job.input) {
    const inputPath = path.resolve(rootDir, inputRel);
    const svgBuffer = await fs.readFile(inputPath);
    cache.set(inputRel, svgBuffer);
    for (const [outputRel, size] of job.output) {
      const { width, height } = parseSize(size);
      const outputPath = path.resolve(rootDir, outputRel);
      await ensureDir(path.dirname(outputPath));
      await sharp(svgBuffer)
        .resize(width, height, { fit: 'cover' })
        .png()
        .toFile(outputPath);
      console.log(`Rendered ${outputRel} (${width}x${height})`);
    }
  }
}

async function main() {
  const configPaths = process.argv.slice(2);
  if (!configPaths.length) {
    console.error('Usage: node render_icons.cjs <config.json> [more...]');
    process.exit(1);
  }
  const rootDir = process.cwd();
  for (const configRel of configPaths) {
    const configPath = path.resolve(rootDir, configRel);
    const raw = await fs.readFile(configPath, 'utf8');
    const jobs = JSON.parse(raw);
    for (const job of jobs) {
      await renderJob(job, rootDir);
    }
  }
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});

#!/usr/bin/env node
/**
 * Generate PWA icons from the SVG logo using sharp.
 * Run from project root: node scripts/generate-icons.mjs
 * Requires: npm install -D sharp
 */
import sharp from 'sharp'
import { readFileSync, mkdirSync } from 'fs'
import { resolve, dirname } from 'path'
import { fileURLToPath } from 'url'

const __dirname = dirname(fileURLToPath(import.meta.url))
const SVG_PATH = resolve(__dirname, '../src/assets/logo-mark.svg')
const PUBLIC_ICONS = resolve(__dirname, '../public/icons')

mkdirSync(PUBLIC_ICONS, { recursive: true })

const svgBuffer = readFileSync(SVG_PATH)

const SIZES = [72, 96, 128, 144, 152, 192, 384, 512]
const BG_COLOR = { r: 36, g: 36, b: 36, alpha: 1 } // #242424

async function generateIcon(size, filename) {
  await sharp(svgBuffer)
    .resize(size, size)
    .flatten({ background: BG_COLOR })
    .png()
    .toFile(resolve(PUBLIC_ICONS, filename))
  console.log(`  Created ${filename}`)
}

async function generateMaskableIcon(size) {
  const innerSize = Math.round(size * 0.7)
  const padding = Math.round((size - innerSize) / 2)
  const filename = `icon-maskable-${size}x${size}.png`

  const innerIcon = await sharp(svgBuffer)
    .resize(innerSize, innerSize)
    .png()
    .toBuffer()

  await sharp({
    create: { width: size, height: size, channels: 4, background: BG_COLOR },
  })
    .composite([{ input: innerIcon, left: padding, top: padding }])
    .png()
    .toFile(resolve(PUBLIC_ICONS, filename))

  console.log(`  Created ${filename}`)
}

console.log('Generating PWA icons...')
for (const size of SIZES) {
  await generateIcon(size, `icon-${size}x${size}.png`)
}
await generateMaskableIcon(192)
await generateMaskableIcon(512)
console.log(`\nDone! Icons saved to: ${PUBLIC_ICONS}`)

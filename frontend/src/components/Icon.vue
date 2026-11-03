<script setup>
// Набор простых линейных значков (собственные рисунки, 24×24, цвет — currentColor).
defineProps({
  name: { type: String, required: true },
  size: { type: [Number, String], default: 18 },
})

const ICONS = {
  plus: ['M12 5v14', 'M5 12h14'],
  x: ['M6 6l12 12', 'M18 6L6 18'],
  check: ['M5 12.5l4.5 4.5L19 7'],
  'arrow-left': ['M19 12H5', 'M11 6l-6 6 6 6'],
  clock: ['circle:12,12,9', 'M12 7v5l3 2'],
  calendar: ['rect:3,5,18,16,2', 'M3 10h18', 'M8 3v4', 'M16 3v4'],
  users: [
    'circle:9,8,3.5',
    'M2.5 20c.6-3.6 3.2-5.5 6.5-5.5s5.9 1.9 6.5 5.5',
    'circle:17,9,2.5',
    'M16.5 14.6c2.6.2 4.4 2 5 4.9',
  ],
  user: ['circle:12,8,4', 'M4 20.5c.9-4 4-6 8-6s7.1 2 8 6'],
  trash: ['M4 7h16', 'M10 11v6', 'M14 11v6', 'M6 7l1 13h10l1-13', 'M9 7V4h6v3'],
  edit: ['M4 20h4L19 9l-4-4L4 16v4z', 'M13.5 6.5l4 4'],
  mail: ['rect:3,5,18,14,2', 'M3.5 6.5l8.5 6.5 8.5-6.5'],
  logout: ['M9 4H5v16h4', 'M14 8l4 4-4 4', 'M18 12H9'],
  trophy: [
    'M8 4h8v5a4 4 0 0 1-8 0V4z',
    'M8 6H5a3 3 0 0 0 3 4',
    'M16 6h3a3 3 0 0 1-3 4',
    'M12 13v4',
    'M8 20h8',
    'M10 17h4',
  ],
  bulb: [
    'M9 18h6',
    'M10 21h4',
    'M12 3a6 6 0 0 0-3.6 10.8c.7.5 1.1 1.3 1.1 2.2h5c0-.9.4-1.7 1.1-2.2A6 6 0 0 0 12 3z',
  ],
  info: ['circle:12,12,9', 'M12 11v5', 'M12 7.6v.4'],
  alert: ['M12 4l9 16H3L12 4z', 'M12 10v4', 'M12 17v.4'],
  refresh: ['M20 12a8 8 0 1 1-2.3-5.6', 'M20 4v4h-4'],
  'eye-off': [
    'M3 3l18 18',
    'M10.6 6.2A9.8 9.8 0 0 1 12 6c5 0 8.5 4 9.5 6-.5 1-1.5 2.5-3 3.8',
    'M6.3 7.8C4.6 9 3.3 10.7 2.5 12c1 2 4.5 6 9.5 6 1.6 0 3-.4 4.3-1',
    'M9.9 10a3 3 0 0 0 4.1 4.1',
  ],
  inbox: ['M3 13h5l1.5 3h5L16 13h5', 'M5 5h14l2 8v6H3v-6l2-8z'],
  vote: ['circle:12,12,9', 'M8 12.5l2.7 2.7L16 9.8'],
  wifi: ['M2.5 9a14 14 0 0 1 19 0', 'M5.5 12.5a9.5 9.5 0 0 1 13 0', 'M8.8 16a5 5 0 0 1 6.4 0', 'M12 19.5v.1'],
  send: ['M21 3L10 14', 'M21 3l-7 18-4-7-7-4 18-7z'],
  chart: ['M4 20V10', 'M10 20V4', 'M16 20v-7', 'M3 20h18'],
  list: ['M9 6h11', 'M9 12h11', 'M9 18h11', 'M4.5 6h.1', 'M4.5 12h.1', 'M4.5 18h.1'],
  bell: ['M6 16V11a6 6 0 0 1 12 0v5l2 2H4l2-2z', 'M10 20.5a2 2 0 0 0 4 0'],
  flag: ['M5 21V4', 'M5 4h12l-2 4 2 4H5'],
}

function parts(name) {
  return (ICONS[name] ?? ICONS.info).map((item) => {
    if (item.startsWith('circle:')) {
      const [cx, cy, r] = item.slice(7).split(',')
      return { tag: 'circle', attrs: { cx, cy, r } }
    }
    if (item.startsWith('rect:')) {
      const [x, y, width, height, rx] = item.slice(5).split(',')
      return { tag: 'rect', attrs: { x, y, width, height, rx } }
    }
    return { tag: 'path', attrs: { d: item } }
  })
}
</script>

<template>
  <svg
    class="icon"
    :width="size"
    :height="size"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    stroke-width="1.9"
    stroke-linecap="round"
    stroke-linejoin="round"
    aria-hidden="true"
    focusable="false"
  >
    <component :is="part.tag" v-for="(part, index) in parts(name)" :key="index" v-bind="part.attrs" />
  </svg>
</template>

<style scoped>
.icon {
  flex: none;
  display: inline-block;
  vertical-align: middle;
}
</style>

<script lang="ts">
	let { size = 28 }: { size?: number } = $props();
</script>

<svg width={size} height={size} viewBox="0 0 32 32" aria-hidden="true">
	<rect x="3" y="5" width="26" height="22" rx="5" fill="none" stroke="var(--accent)" stroke-width="2" />
	<path d="M3 11h26" stroke="var(--accent)" stroke-width="2" opacity="0.45" />
	<circle cx="16" cy="18" r="4.2" fill="none" stroke="var(--accent)" stroke-width="2" />
	<path d="M16 18v3.4" stroke="var(--accent)" stroke-width="2" stroke-linecap="round" />
</svg>

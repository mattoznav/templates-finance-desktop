<script lang="ts">
	import type { Snippet } from 'svelte';

	interface Props {
		title: string;
		subtitle?: string;
		width?: number;
		onclose: () => void;
		children: Snippet;
		footer?: Snippet;
	}

	let { title, subtitle, width = 520, onclose, children, footer }: Props = $props();
	let dialog: HTMLDialogElement;

	$effect(() => {
		dialog.showModal();
		return () => dialog.close();
	});
</script>

<dialog
	bind:this={dialog}
	style:width="{width}px"
	oncancel={(e) => {
		e.preventDefault();
		onclose();
	}}
	onclick={(e) => {
		if (e.target === dialog) onclose();
	}}
>
	<div class="inner">
		<header>
			<div>
				<h2>{title}</h2>
				{#if subtitle}<p class="muted">{subtitle}</p>{/if}
			</div>
			<button class="btn ghost small close" onclick={onclose} aria-label="Close">✕</button>
		</header>
		<div class="body">{@render children()}</div>
		{#if footer}<footer>{@render footer()}</footer>{/if}
	</div>
</dialog>

<style>
	dialog {
		max-width: calc(100vw - 40px);
		max-height: calc(100vh - 60px);
		padding: 0;
		border: 1px solid var(--line-strong);
		border-radius: 14px;
		background: var(--surface);
		color: var(--text);
		box-shadow: var(--shadow);
		overflow: hidden;
	}

	dialog::backdrop {
		background: rgba(5, 6, 7, 0.55);
		backdrop-filter: blur(3px);
	}

	dialog[open] {
		animation: rise 0.16s ease-out;
	}

	@keyframes rise {
		from {
			opacity: 0;
			transform: translateY(6px) scale(0.99);
		}
	}

	.inner {
		display: flex;
		flex-direction: column;
		max-height: calc(100vh - 60px);
	}

	header {
		display: flex;
		justify-content: space-between;
		align-items: flex-start;
		gap: 12px;
		padding: 20px 22px 4px;
	}

	header h2 {
		font-size: 17px;
	}

	header p {
		margin-top: 3px;
		font-size: 13px;
	}

	.body {
		padding: 16px 22px 20px;
		overflow: auto;
		display: flex;
		flex-direction: column;
		gap: 14px;
	}

	footer {
		display: flex;
		justify-content: flex-end;
		gap: 8px;
		padding: 14px 22px;
		border-top: 1px solid var(--line);
		background: var(--surface-2);
	}

	.close {
		margin: -4px -8px 0 0;
	}
</style>

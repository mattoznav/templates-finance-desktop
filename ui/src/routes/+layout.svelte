<script lang="ts">
	import '../app.css';
	import favicon from '#lib/assets/favicon.svg';
	import { page } from '$app/state';
	import { ApiError } from '#lib/api.ts';
	import Icon, { type IconName } from '#lib/components/Icon.svelte';
	import LockScreen from '#lib/components/LockScreen.svelte';
	import Logo from '#lib/components/Logo.svelte';
	import Modal from '#lib/components/Modal.svelte';
	import { confirmations } from '#lib/confirm.svelte.ts';
	import { session } from '#lib/session.svelte.ts';
	import { toasts } from '#lib/toast.svelte.ts';
	import type { LayoutProps } from './$types';

	let { children }: LayoutProps = $props();
	let failure = $state('');

	const NAV: { href: string; label: string; icon: IconName }[] = [
		{ href: '/', label: 'Overview', icon: 'overview' },
		{ href: '/accounts', label: 'Accounts', icon: 'accounts' },
		{ href: '/transactions', label: 'Transactions', icon: 'transactions' },
		{ href: '/budget', label: 'Budget', icon: 'budget' },
		{ href: '/investments', label: 'Investments', icon: 'investments' },
		{ href: '/import', label: 'Import', icon: 'import' },
		{ href: '/settings', label: 'Settings', icon: 'settings' }
	];

	$effect(() => {
		session.refresh().catch((err) => {
			failure = err instanceof ApiError ? err.message : String(err);
		});
		return session.start();
	});

	let path = $derived(page.route.id ?? '/');
	let minutesLeft = $derived(Math.ceil((session.status?.seconds_left ?? 0) / 60));

	function active(href: string) {
		return href === '/' ? path === '/' : path.startsWith(href);
	}
</script>

<svelte:head>
	<title>Coffer</title>
	<link rel="icon" href={favicon} />
</svelte:head>

{#if failure}
	<div class="center">
		<Logo size={40} />
		<p>{failure}</p>
		<p class="muted">Start the core with <code>python -m coffer.devserver</code> and reload.</p>
	</div>
{:else if !session.status}
	<div class="center"><Logo size={40} /></div>
{:else if !session.unlocked}
	<LockScreen />
{:else}
	<div class="shell">
		<nav>
			<div class="brand"><Logo size={26} /><span>Coffer</span></div>
			<ul>
				{#each NAV as item (item.href)}
					<li>
						<a href="#{item.href}" class:active={active(item.href)}>
							<Icon name={item.icon} />
							{item.label}
						</a>
					</li>
				{/each}
			</ul>
			<div class="foot">
				{#if session.status.demo}
					<div class="demo-note">
						<strong>Demo data</strong>
						Nothing you change is saved.
					</div>
				{:else}
					<p class="faint">Auto-lock in {minutesLeft} min</p>
				{/if}
				<button class="btn lock-btn" onclick={() => session.lock()}>
					<Icon name="lock" size={16} />
					{session.status.demo ? 'Leave demo' : 'Lock now'}
				</button>
			</div>
		</nav>
		<main>
			{@render children()}
		</main>
	</div>
{/if}

<div class="toasts" aria-live="polite">
	{#each toasts.items as toast (toast.id)}
		<button class="toast" class:error={toast.tone === 'error'} onclick={() => toasts.dismiss(toast.id)}>{toast.text}</button>
	{/each}
</div>

{#if confirmations.current}
	{@const request = confirmations.current}
	<Modal title={request.title} width={420} onclose={() => confirmations.answer(false)}>
		<p class="muted">{request.message}</p>
		{#snippet footer()}
			<button class="btn" onclick={() => confirmations.answer(false)}>Cancel</button>
			<button class="btn {request.danger ? 'danger' : 'primary'}" onclick={() => confirmations.answer(true)}>
				{request.confirm ?? 'Confirm'}
			</button>
		{/snippet}
	</Modal>
{/if}

<style>
	.center {
		display: grid;
		place-items: center;
		align-content: center;
		gap: 12px;
		min-height: 100vh;
		text-align: center;
	}

	.shell {
		display: grid;
		grid-template-columns: 220px 1fr;
		height: 100vh;
	}

	nav {
		display: flex;
		flex-direction: column;
		padding: 20px 12px 16px;
		background: var(--sidebar);
		border-right: 1px solid var(--line);
	}

	.brand {
		display: flex;
		align-items: center;
		gap: 10px;
		padding: 0 10px 22px;
		font-family: var(--font-display);
		font-size: 19px;
	}

	ul {
		list-style: none;
		margin: 0;
		padding: 0;
		display: grid;
		gap: 2px;
	}

	nav a {
		display: flex;
		align-items: center;
		gap: 11px;
		padding: 8px 10px;
		border-radius: var(--radius-sm);
		color: var(--muted);
		text-decoration: none;
		font-weight: 500;
	}

	nav a:hover {
		color: var(--text);
		background: var(--surface-2);
	}

	nav a.active {
		color: var(--text);
		background: var(--surface-3);
	}

	nav a.active :global(svg) {
		color: var(--accent);
	}

	.foot {
		margin-top: auto;
		display: grid;
		gap: 10px;
		padding: 0 4px;
		font-size: 12px;
	}

	.foot p {
		padding: 0 6px;
	}

	.demo-note {
		padding: 10px 12px;
		border-radius: var(--radius-sm);
		background: var(--accent-soft);
		color: var(--muted);
	}

	.demo-note strong {
		display: block;
		color: var(--accent);
	}

	.lock-btn {
		width: 100%;
	}

	main {
		overflow: auto;
		min-width: 0;
	}

	.toasts {
		position: fixed;
		right: 20px;
		bottom: 20px;
		display: grid;
		gap: 8px;
		z-index: 100;
	}

	.toast {
		max-width: 380px;
		padding: 11px 15px;
		border-radius: var(--radius-sm);
		border: 1px solid var(--line-strong);
		background: var(--surface-3);
		box-shadow: var(--shadow);
		text-align: left;
		cursor: pointer;
		animation: in 0.18s ease-out;
	}

	.toast.error {
		border-color: color-mix(in srgb, var(--neg) 50%, transparent);
		color: var(--neg);
	}

	@keyframes in {
		from {
			opacity: 0;
			transform: translateY(6px);
		}
	}
</style>

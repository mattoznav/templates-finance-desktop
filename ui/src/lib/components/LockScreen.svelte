<script lang="ts">
	import { ApiError, readFileBase64, rpc } from '#lib/api.ts';
	import { session } from '#lib/session.svelte.ts';
	import type { Status } from '#lib/types.ts';
	import Icon from './Icon.svelte';
	import Logo from './Logo.svelte';
	import RecoveryKey from './RecoveryKey.svelte';

	type Mode = 'unlock' | 'create' | 'recover' | 'restore' | 'show-key';

	let mode = $state<Mode>(session.status?.vault_exists ? 'unlock' : 'create');
	let password = $state('');
	let confirm = $state('');
	let recoveryKey = $state('');
	let backupFile = $state<File | null>(null);
	let newKey = $state('');
	let busy = $state(false);
	let error = $state('');

	const lockedByTimeout = session.lockedByTimeout;

	function go(next: Mode) {
		mode = next;
		error = '';
		password = '';
		confirm = '';
	}

	function strength(value: string): { score: number; label: string } {
		if (value.length < 10) return { score: Math.min(value.length / 10, 0.9) * 0.25, label: 'At least 10 characters' };
		const classes = [/[a-z]/, /[A-Z]/, /\d/, /[^a-zA-Z\d]/].filter((r) => r.test(value)).length;
		const words = value.trim().split(/\s+/).length;
		if (value.length >= 18 || (value.length >= 14 && (classes >= 3 || words >= 3))) return { score: 1, label: 'Strong' };
		if (value.length >= 12 && classes >= 2) return { score: 0.7, label: 'Good' };
		return { score: 0.45, label: 'Fair: longer is better' };
	}

	let meter = $derived(strength(password));

	async function run(action: () => Promise<void>) {
		busy = true;
		error = '';
		try {
			await action();
		} catch (err) {
			error = err instanceof ApiError ? err.message : String(err);
		} finally {
			busy = false;
		}
	}

	const unlock = () =>
		run(async () => {
			session.apply(await rpc<Status>('unlock', { password }));
			session.changed();
		});

	const create = () =>
		run(async () => {
			if (password !== confirm) throw new Error('The two passwords do not match');
			const result = await rpc<{ recovery_key: string }>('create_vault', { password });
			newKey = result.recovery_key;
			mode = 'show-key';
		});

	const recover = () =>
		run(async () => {
			if (password !== confirm) throw new Error('The two passwords do not match');
			const status = await rpc<Status>('recover', { recovery_key: recoveryKey, new_password: password });
			session.apply(status);
			session.changed();
		});

	const restore = () =>
		run(async () => {
			if (!backupFile) throw new Error('Choose a backup file');
			const data = await readFileBase64(backupFile);
			session.apply(await rpc<Status>('restore_backup', { data, password }));
			session.changed();
		});

	const demo = () =>
		run(async () => {
			session.apply(await rpc<Status>('open_demo'));
			session.changed();
		});

	async function finishCreate() {
		await session.refresh();
		session.changed();
	}
</script>

<div class="lock">
	<aside>
		<div class="brand"><Logo size={34} /><span>Coffer</span></div>
		<div class="pitch">
			<h1>Your money, on your machine.</h1>
			<p>
				Accounts, budgets, net worth and investments in one place. No server, no sign-up, no bank
				connections: everything is encrypted and stays on this device.
			</p>
		</div>
		<ul>
			<li><Icon name="shield" /><span><strong>AES-256-GCM</strong> encryption, key derived from your password with Argon2id</span></li>
			<li><Icon name="lock" /><span><strong>Locks itself</strong> after a few minutes away</span></li>
			<li><Icon name="key" /><span><strong>Recovery key</strong> in case you forget the password</span></li>
		</ul>
	</aside>

	<main>
		<div class="panel">
			{#if mode === 'unlock'}
				<h2>Unlock your vault</h2>
				<p class="muted">{lockedByTimeout ? 'Coffer locked itself while you were away.' : 'Enter your master password.'}</p>
				<form onsubmit={(e) => (e.preventDefault(), unlock())}>
					<label class="field">
						<span>Master password</span>
						<!-- svelte-ignore a11y_autofocus -->
						<input class="input" type="password" bind:value={password} autocomplete="current-password" autofocus />
					</label>
					{#if error}<p class="error-text">{error}</p>{/if}
					<button class="btn primary large" disabled={busy || !password}>{busy ? 'Unlocking…' : 'Unlock'}</button>
				</form>
				<div class="links">
					<button class="link" onclick={() => go('recover')}>Forgot the password?</button>
					<button class="link" onclick={() => go('restore')}>Restore a backup</button>
				</div>
			{:else if mode === 'create'}
				<h2>Create your vault</h2>
				<p class="muted">Choose a master password. It never leaves this device and cannot be reset by anyone.</p>
				<form onsubmit={(e) => (e.preventDefault(), create())}>
					<label class="field">
						<span>Master password</span>
						<!-- svelte-ignore a11y_autofocus -->
						<input class="input" type="password" bind:value={password} autocomplete="new-password" autofocus />
					</label>
					<div class="meter" aria-live="polite">
						<div class="bar"><i style:width="{meter.score * 100}%" style:background={meter.score >= 0.7 ? 'var(--pos)' : meter.score >= 0.45 ? 'var(--warn)' : 'var(--neg)'}></i></div>
						<small class="muted">{password ? meter.label : 'A few unrelated words make a strong password'}</small>
					</div>
					<label class="field">
						<span>Repeat it</span>
						<input class="input" type="password" bind:value={confirm} autocomplete="new-password" />
					</label>
					{#if error}<p class="error-text">{error}</p>{/if}
					<button class="btn primary large" disabled={busy || password.length < 10 || !confirm}>
						{busy ? 'Creating…' : 'Create vault'}
					</button>
				</form>
				<div class="links">
					<button class="link" onclick={() => go('restore')}>Restore a backup instead</button>
				</div>
			{:else if mode === 'recover'}
				<h2>Use your recovery key</h2>
				<p class="muted">The 32-character key you saved when you created the vault. Then choose a new password.</p>
				<form onsubmit={(e) => (e.preventDefault(), recover())}>
					<label class="field">
						<span>Recovery key</span>
						<input class="input mono" bind:value={recoveryKey} placeholder="XXXX-XXXX-XXXX-XXXX-XXXX-XXXX-XXXX-XXXX" autocomplete="off" spellcheck="false" />
					</label>
					<label class="field">
						<span>New master password</span>
						<input class="input" type="password" bind:value={password} autocomplete="new-password" />
					</label>
					<label class="field">
						<span>Repeat it</span>
						<input class="input" type="password" bind:value={confirm} autocomplete="new-password" />
					</label>
					{#if error}<p class="error-text">{error}</p>{/if}
					<button class="btn primary large" disabled={busy || !recoveryKey || password.length < 10}>
						{busy ? 'Checking…' : 'Reset password and unlock'}
					</button>
				</form>
				<div class="links"><button class="link" onclick={() => go('unlock')}>Back</button></div>
			{:else if mode === 'restore'}
				<h2>Restore a backup</h2>
				<p class="muted">Pick a <code>.coffer</code> backup and enter the password it was saved with.</p>
				<form onsubmit={(e) => (e.preventDefault(), restore())}>
					<label class="field">
						<span>Backup file</span>
						<input class="input file" type="file" accept=".coffer,application/json" onchange={(e) => (backupFile = (e.target as HTMLInputElement).files?.[0] ?? null)} />
					</label>
					<label class="field">
						<span>Password of that backup</span>
						<input class="input" type="password" bind:value={password} autocomplete="current-password" />
					</label>
					{#if session.status?.vault_exists}
						<p class="notice">The vault on this device is kept as a copy next to the restored one, not deleted.</p>
					{/if}
					{#if error}<p class="error-text">{error}</p>{/if}
					<button class="btn primary large" disabled={busy || !backupFile || !password}>{busy ? 'Restoring…' : 'Restore and unlock'}</button>
				</form>
				<div class="links"><button class="link" onclick={() => go(session.status?.vault_exists ? 'unlock' : 'create')}>Back</button></div>
			{:else if mode === 'show-key'}
				<RecoveryKey value={newKey} onDone={finishCreate} />
			{/if}
		</div>

		{#if mode !== 'show-key'}
			<button class="demo" onclick={demo} disabled={busy}>
				<span>Just looking?</span> Explore Coffer with demo data <Icon name="right" size={15} />
			</button>
		{/if}
	</main>
</div>

<style>
	.lock {
		display: grid;
		grid-template-columns: minmax(360px, 0.9fr) 1.1fr;
		min-height: 100vh;
	}

	aside {
		position: relative;
		display: flex;
		flex-direction: column;
		justify-content: space-between;
		padding: 40px 44px;
		background:
			radial-gradient(120% 70% at 0% 100%, var(--accent-soft), transparent 60%),
			var(--sidebar);
		border-right: 1px solid var(--line);
	}

	.brand {
		display: flex;
		align-items: center;
		gap: 11px;
		font-family: var(--font-display);
		font-size: 22px;
	}

	.pitch h1 {
		font-size: 40px;
		line-height: 1.08;
		max-width: 12ch;
	}

	.pitch p {
		margin-top: 16px;
		color: var(--muted);
		max-width: 40ch;
		font-size: 15px;
	}

	ul {
		list-style: none;
		margin: 0;
		padding: 0;
		display: grid;
		gap: 14px;
		color: var(--muted);
		font-size: 13px;
	}

	li {
		display: flex;
		gap: 11px;
		align-items: flex-start;
	}

	li :global(svg) {
		flex: none;
		color: var(--accent);
		margin-top: 1px;
	}

	li strong {
		color: var(--text);
		font-weight: 600;
	}

	main {
		display: flex;
		flex-direction: column;
		align-items: center;
		justify-content: center;
		gap: 22px;
		padding: 40px;
	}

	.panel {
		width: min(420px, 100%);
	}

	.panel h2 {
		font-size: 22px;
		font-family: var(--font-display);
		font-weight: 500;
	}

	.panel > p {
		margin-top: 6px;
	}

	form {
		display: flex;
		flex-direction: column;
		gap: 14px;
		margin-top: 24px;
	}

	form .btn {
		margin-top: 6px;
	}

	.meter {
		display: grid;
		gap: 6px;
		margin-top: -6px;
	}

	.links {
		display: flex;
		justify-content: space-between;
		margin-top: 18px;
	}

	.link {
		border: 0;
		background: none;
		padding: 0;
		color: var(--muted);
		cursor: pointer;
		font-size: 13px;
	}

	.link:hover {
		color: var(--text);
		text-decoration: underline;
	}

	.mono {
		font-family: var(--font-mono);
		letter-spacing: 0.04em;
	}

	.file {
		padding-top: 6px;
	}

	.demo {
		display: inline-flex;
		align-items: center;
		gap: 8px;
		border: 1px dashed var(--line-strong);
		background: transparent;
		color: var(--text);
		padding: 10px 16px;
		border-radius: 999px;
		cursor: pointer;
	}

	.demo span {
		color: var(--muted);
	}

	.demo:hover {
		border-color: var(--accent);
	}

	@media (max-width: 900px) {
		.lock {
			grid-template-columns: 1fr;
		}

		aside {
			display: none;
		}
	}
</style>

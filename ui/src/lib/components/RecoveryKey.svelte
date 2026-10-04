<script lang="ts">
	let { value, onDone, doneLabel = 'Continue to Coffer' }: { value: string; onDone: () => void; doneLabel?: string } = $props();
	let stored = $state(false);
	let copied = $state(false);

	async function copy() {
		try {
			await navigator.clipboard.writeText(value);
			copied = true;
			setTimeout(() => (copied = false), 2000);
		} catch {
			copied = false;
		}
	}
</script>

<div class="recovery">
	<h2>Save your recovery key</h2>
	<p class="muted">
		If you forget the master password, this key is the only way back in. There is no server and no
		reset email: without the password or this key, the data cannot be opened by anyone.
	</p>
	<div class="key" aria-label="Recovery key">
		{#each value.split('-') as group, i (i)}<span>{group}</span>{/each}
	</div>
	<div class="actions">
		<button class="btn small" onclick={copy}>{copied ? 'Copied' : 'Copy'}</button>
		<span class="faint">Write it down or keep it in a password manager. It is shown only now.</span>
	</div>
	<label class="check">
		<input type="checkbox" bind:checked={stored} />
		I have stored the recovery key somewhere safe
	</label>
	<button class="btn primary large" disabled={!stored} onclick={onDone}>{doneLabel}</button>
</div>

<style>
	.recovery {
		display: flex;
		flex-direction: column;
		gap: 16px;
	}

	h2 {
		font-size: 22px;
		font-family: var(--font-display);
		font-weight: 500;
	}

	.key {
		display: grid;
		grid-template-columns: repeat(4, 1fr);
		gap: 8px;
		padding: 16px;
		border-radius: var(--radius);
		background: var(--surface-2);
		border: 1px solid var(--line-strong);
		font-family: var(--font-mono);
		font-size: 17px;
		letter-spacing: 0.08em;
		text-align: center;
		user-select: all;
	}

	.actions {
		font-size: 12px;
	}
</style>

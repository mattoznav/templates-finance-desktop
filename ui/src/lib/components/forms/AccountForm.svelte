<script lang="ts">
	import { untrack } from 'svelte';
	import { rpc } from '#lib/api.ts';
	import { confirmAction } from '#lib/confirm.svelte.ts';
	import { ACCOUNT_KINDS, today } from '#lib/format.ts';
	import { session } from '#lib/session.svelte.ts';
	import { toasts } from '#lib/toast.svelte.ts';
	import type { Account } from '#lib/types.ts';
	import Modal from '../Modal.svelte';
	import MoneyInput from '../MoneyInput.svelte';

	let { account, onclose }: { account: Partial<Account> | null; onclose: () => void } = $props();

	let form = $state(
		untrack(() => ({
			id: account?.id,
			name: account?.name ?? '',
			kind: account?.kind ?? 'checking',
			institution: account?.institution ?? '',
			opening_balance: account?.opening_balance ?? 0,
			opening_date: account?.opening_date ?? today(),
			archived: account?.archived ?? false
		}))
	);
	let busy = $state(false);

	async function save(event: SubmitEvent) {
		event.preventDefault();
		busy = true;
		try {
			await rpc('save_account', { account: { ...form, opening_balance: form.opening_balance ?? 0 } });
			toasts.show(form.id ? 'Account updated' : 'Account added');
			session.changed();
			onclose();
		} catch (err) {
			toasts.error(err);
		} finally {
			busy = false;
		}
	}

	async function remove() {
		const ok = await confirmAction({
			title: `Delete ${form.name}?`,
			message: `This removes the account and its ${account?.movements ?? 0} movements, including both sides of its transfers. Archive it instead to keep the history.`,
			confirm: 'Delete account',
			danger: true
		});
		if (!ok) return;
		try {
			await rpc('delete_account', { id: form.id });
			toasts.show('Account deleted');
			session.changed();
			onclose();
		} catch (err) {
			toasts.error(err);
		}
	}
</script>

<Modal title={form.id ? 'Edit account' : 'New account'} {onclose}>
	<form id="account-form" class="grid" onsubmit={save}>
		<label class="field">
			<span>Name</span>
			<!-- svelte-ignore a11y_autofocus -->
			<input class="input" bind:value={form.name} placeholder="Everyday" autofocus required />
		</label>
		<div class="row">
			<label class="field">
				<span>Type</span>
				<select class="input" bind:value={form.kind}>
					{#each Object.entries(ACCOUNT_KINDS) as [value, label] (value)}<option {value}>{label}</option>{/each}
				</select>
			</label>
			<label class="field">
				<span>Bank or provider</span>
				<input class="input" bind:value={form.institution} placeholder="Optional" />
			</label>
		</div>
		<div class="row">
			<label class="field">
				<span>Balance on the start date</span>
				<MoneyInput bind:value={form.opening_balance} allowNegative />
			</label>
			<label class="field">
				<span>Start date</span>
				<input class="input" type="date" bind:value={form.opening_date} />
			</label>
		</div>
		<small class="faint">
			Pick the day before the first transaction you will record or import. A credit card that owes money starts negative.
		</small>
		{#if form.id}
			<label class="check"><input type="checkbox" bind:checked={form.archived} /> Archived: hidden from the overview, kept in history</label>
		{/if}
	</form>
	{#snippet footer()}
		{#if form.id}<button class="btn danger" type="button" onclick={remove}>Delete</button><span style="flex:1"></span>{/if}
		<button class="btn" type="button" onclick={onclose}>Cancel</button>
		<button class="btn primary" form="account-form" disabled={busy || !form.name.trim()}>Save</button>
	{/snippet}
</Modal>

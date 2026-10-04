<script lang="ts">
	import { untrack } from 'svelte';
	import { rpc } from '#lib/api.ts';
	import { today } from '#lib/format.ts';
	import { session } from '#lib/session.svelte.ts';
	import { toasts } from '#lib/toast.svelte.ts';
	import type { Account } from '#lib/types.ts';
	import Modal from '../Modal.svelte';
	import MoneyInput from '../MoneyInput.svelte';

	let { accounts, onclose }: { accounts: Account[]; onclose: () => void } = $props();
	let open = $derived(accounts.filter((a) => !a.archived));

	let form = $state(
		untrack(() => ({
			from_account_id: accounts.find((a) => !a.archived)?.id,
			to_account_id: accounts.filter((a) => !a.archived)[1]?.id,
			amount: null as number | null,
			date: today(),
			note: ''
		}))
	);
	let busy = $state(false);

	async function save(event: SubmitEvent) {
		event.preventDefault();
		busy = true;
		try {
			await rpc('save_transfer', { transfer: form });
			toasts.show('Transfer recorded');
			session.changed();
			onclose();
		} catch (err) {
			toasts.error(err);
		} finally {
			busy = false;
		}
	}
</script>

<Modal title="Move money between accounts" subtitle="Transfers do not count as income or spending." {onclose}>
	<form id="transfer-form" class="grid" onsubmit={save}>
		<div class="row">
			<label class="field">
				<span>From</span>
				<select class="input" bind:value={form.from_account_id}>
					{#each open as a (a.id)}<option value={a.id}>{a.name}</option>{/each}
				</select>
			</label>
			<label class="field">
				<span>To</span>
				<select class="input" bind:value={form.to_account_id}>
					{#each open as a (a.id)}<option value={a.id}>{a.name}</option>{/each}
				</select>
			</label>
		</div>
		<div class="row">
			<label class="field"><span>Amount</span><MoneyInput bind:value={form.amount} /></label>
			<label class="field"><span>Date</span><input class="input" type="date" bind:value={form.date} /></label>
		</div>
		<label class="field"><span>Note</span><input class="input" bind:value={form.note} placeholder="Optional" /></label>
		{#if form.from_account_id === form.to_account_id}<p class="error-text">Choose two different accounts.</p>{/if}
	</form>
	{#snippet footer()}
		<button class="btn" type="button" onclick={onclose}>Cancel</button>
		<button class="btn primary" form="transfer-form" disabled={busy || !form.amount || form.from_account_id === form.to_account_id}>Record transfer</button>
	{/snippet}
</Modal>

// Transaction filters survive navigation, so "see transactions" links from
// other pages can preset them.
export const txFilters = $state({
	account_id: '' as string,
	category_id: '' as string,
	search: '',
	from: '',
	to: ''
});

export function resetTxFilters(patch: Partial<typeof txFilters> = {}): void {
	Object.assign(txFilters, { account_id: '', category_id: '', search: '', from: '', to: '' }, patch);
}

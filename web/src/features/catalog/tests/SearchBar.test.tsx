import { act, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import SearchBar from '../components/SearchBar';

const noop = () => undefined;

describe('SearchBar', () => {
  it('invokes submit handler with current value', async () => {
    const user = userEvent.setup();
    const handleSubmit = vi.fn();

    render(
      <SearchBar
        value=""
        onChange={noop}
        onSubmit={handleSubmit}
        filters={['albums']}
        onToggleFilter={noop}
      />
    );

    await act(async () => {
      await user.type(screen.getByPlaceholderText('Scan the catalog…'), 'nirvana');
      await user.click(screen.getByRole('button', { name: /query/i }));
    });

    expect(handleSubmit).toHaveBeenCalledWith('nirvana');
  });
});

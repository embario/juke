import type { Meta, StoryObj } from '@storybook/react';
import StatusBanner from './StatusBanner';

const meta = {
  title: 'UIKit/StatusBanner',
  component: StatusBanner,
  tags: ['autodocs'],
  args: {
    message: 'System notice goes here.',
  },
} satisfies Meta<typeof StatusBanner>;

export default meta;

type Story = StoryObj<typeof meta>;

export const Info: Story = {
  args: {
    variant: 'info',
  },
};

export const Success: Story = {
  args: {
    variant: 'success',
  },
};

export const Warning: Story = {
  args: {
    variant: 'warning',
  },
};

export const Error: Story = {
  args: {
    variant: 'error',
    message: 'Something went wrong with your request.',
  },
};

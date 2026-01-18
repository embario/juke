import type { Meta, StoryObj } from '@storybook/react';
import Button from './Button';

const meta = {
  title: 'UIKit/Button',
  component: Button,
  tags: ['autodocs'],
  args: {
    children: 'Click me',
    type: 'button',
  },
} satisfies Meta<typeof Button>;

export default meta;

type Story = StoryObj<typeof meta>;

export const Primary: Story = {
  args: {
    variant: 'primary',
  },
};

export const Ghost: Story = {
  args: {
    variant: 'ghost',
  },
};

export const LinkStyle: Story = {
  args: {
    variant: 'link',
  },
};

export const Disabled: Story = {
  args: {
    disabled: true,
  },
};

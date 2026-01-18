import type { Meta, StoryObj } from '@storybook/react';
import InputField from './InputField';

const meta = {
  title: 'UIKit/InputField',
  component: InputField,
  tags: ['autodocs'],
  args: {
    label: 'Username',
    name: 'username',
    placeholder: 'analyst@juke',
  },
} satisfies Meta<typeof InputField>;

export default meta;

type Story = StoryObj<typeof meta>;

export const Default: Story = {};

export const WithError: Story = {
  args: {
    error: 'This field is required.',
  },
};

export const Password: Story = {
  args: {
    label: 'Password',
    name: 'password',
    type: 'password',
    placeholder: '••••••••',
  },
};

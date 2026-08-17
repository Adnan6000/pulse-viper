# core/experience_memory.py
import numpy as np
import pandas as pd
from collections import deque, defaultdict
import pickle
import json
import os
from typing import Dict, List, Optional, Any
import logging

class ExperienceMemory:
    def __init__(self, capacity=5000):
        self.capacity = capacity
        self.memory = deque(maxlen=capacity)
        self.position = 0
        self.performance_stats = {
            'total_trades': 0,
            'winning_trades': 0,
            'losing_trades': 0,
            'total_pnl': 0.0,
            'winning_pnl_sum': 0.0,
            'losing_pnl_sum': 0.0,
            'max_win': -np.inf,
            'max_loss': np.inf,
            'avg_win': 0.0,
            'avg_loss': 0.0
        }
        self.logger = logging.getLogger('PulseViper.Memory')
        self.load_memory()
        
    def store(self, state: Dict, action: int, reward: float, 
              next_state: Dict, done: bool, metadata: Optional[Dict] = None):
        """Store trading experience with comprehensive tracking"""
        experience = {
            'state': state,           # Market state/features
            'action': action,         # 0=Hold, 1=Buy, 2=Sell
            'reward': reward,         # PnL from the trade
            'next_state': next_state, # State after action
            'done': done,            # Episode complete
            'timestamp': pd.Timestamp.now(),
            'metadata': metadata or {}  # Additional trade info
        }
        
        self.memory.append(experience)
        self._update_performance_stats(reward, metadata)
        self.position = (self.position + 1) % self.capacity
        self.save_memory()
        
        self.logger.debug(f"Stored experience #{len(self.memory)} | Reward: {reward:.4f}")
        
    def _update_performance_stats(self, reward: float, metadata: Dict):
        """Update trading performance statistics using actual PnL rewards"""
        self.performance_stats['total_trades'] += 1
        self.performance_stats['total_pnl'] += reward
        
        if reward > 0:
            self.performance_stats['winning_trades'] += 1
            self.performance_stats['winning_pnl_sum'] += reward
            self.performance_stats['max_win'] = max(self.performance_stats['max_win'], reward)
        else:
            self.performance_stats['losing_trades'] += 1
            self.performance_stats['losing_pnl_sum'] += reward
            self.performance_stats['max_loss'] = min(self.performance_stats['max_loss'], reward)
            
        w_trades = self.performance_stats['winning_trades']
        l_trades = self.performance_stats['losing_trades']
        
        self.performance_stats['avg_win'] = self.performance_stats['winning_pnl_sum'] / w_trades if w_trades > 0 else 0.0
        self.performance_stats['avg_loss'] = self.performance_stats['losing_pnl_sum'] / l_trades if l_trades > 0 else 0.0
    
    def sample(self, batch_size: int, prioritized: bool = False) -> Optional[List]:
        """Sample random experiences for learning"""
        if len(self.memory) < batch_size:
            return None
            
        if prioritized:
            rewards = np.array([exp['reward'] for exp in self.memory])
            priorities = np.abs(rewards - np.mean(rewards)) + 1e-5
            probabilities = priorities / np.sum(priorities)
            indices = np.random.choice(len(self.memory), batch_size, p=probabilities, replace=False)
        else:
            indices = np.random.choice(len(self.memory), batch_size, replace=False)
            
        return [self.memory[i] for i in indices]
    
    def get_recent(self, n: int) -> List:
        """Get most recent experiences"""
        return list(self.memory)[-n:]
    
    def get_high_reward_experiences(self, threshold: float = 0.0) -> List:
        """Get experiences with rewards above threshold"""
        return [exp for exp in self.memory if exp['reward'] >= threshold]
    
    def get_performance_metrics(self) -> Dict:
        """Get comprehensive performance metrics"""
        if self.performance_stats['total_trades'] == 0:
            return self.performance_stats
            
        stats = self.performance_stats.copy()
        stats['win_rate'] = (stats['winning_trades'] / stats['total_trades']) * 100
        stats['avg_trade'] = stats['total_pnl'] / stats['total_trades']
        
        gross_profit = stats.get('winning_pnl_sum', 0.0)
        gross_loss = abs(stats.get('losing_pnl_sum', 0.0))
        stats['profit_factor'] = gross_profit / (gross_loss + 1e-10)
        
        # Clean up numpy types for json serialization compatibility
        for k in ['max_win', 'max_loss']:
            if np.isinf(stats[k]):
                stats[k] = 0.0
                
        return stats
    
    def save_memory(self, filepath: str = 'data/experience_memory.pkl'):
        """Save experience memory to disk"""
        try:
            os.makedirs(os.path.dirname(filepath), exist_ok=True)
            with open(filepath, 'wb') as f:
                pickle.dump({
                    'memory': list(self.memory),
                    'performance_stats': self.performance_stats,
                    'position': self.position
                }, f)
        except Exception as e:
            self.logger.error(f"Failed to save experience memory: {e}")
    
    def load_memory(self, filepath: str = 'data/experience_memory.pkl'):
        """Load experience memory from disk"""
        if os.path.exists(filepath):
            try:
                with open(filepath, 'rb') as f:
                    data = pickle.load(f)
                    self.memory = deque(data['memory'], maxlen=self.capacity)
                    self.performance_stats = data['performance_stats']
                    self.position = data['position']
                self.logger.info(f"Memory loaded from {filepath} with {len(self.memory)} experiences")
            except Exception as e:
                self.logger.warning(f"Failed to load memory from {filepath}: {e}, starting fresh")
    
    def __len__(self):
        return len(self.memory)
    
    def __str__(self):
        stats = self.get_performance_metrics()
        return (f"ExperienceMemory(trades={len(self.memory)}, "
                f"win_rate={stats.get('win_rate', 0):.1f}%, "
                f"total_pnl={stats['total_pnl']:.2f})")
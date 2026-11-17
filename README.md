# pairwise-particle-system

特效组反馈粒子发射数量随帧率变化，同样的爆炸在 30 帧和 120 帧下密度差一倍，粒子飞出去像纸片一样匀速直线运动，落地不弹也不停，半透明粒子叠在一起边缘发黑，远处粒子多到帧率掉到 20。查下来是 render/particles.py 的粒子系统有严重问题：emission_count() 直接把速率乘时间取整，小数部分丢掉，低帧率下越积越少；update_particle() 不积分重力和阻尼，速度永远不变；lifetime_alpha() 恒返回 1，出生不淡入、死亡不淡出，粒子是突然出现突然消失；kill_expired() 只加年龄不回收，死粒子永远留在池子里；pack_instances() 每粒子只写 2 个 float，GPU 拿到的步长完全不对；sort_particles() 不按深度排序，透明混合顺序错乱；cull_particles() 不做视锥剔除；lod_stride() 恒为 1，超预算也不降采样；limit_emission() 不看容量，粒子数无限增长；bounce() 落地只把速度清零，没有恢复系数；interpolate_position() 直接返回当前帧，快速粒子在两帧之间瞬移；color_over_life() 恒返回起始颜色。你要修的是：发射按累积余数补齐；速度积分包含重力和阻尼；透明度按生命周期淡入淡出；过期粒子回收；实例缓冲固定 8 float 步长；按深度从远到近排序；视锥剔除；按预算降采样；发射受容量限制；落地按恢复系数反弹；位置按子帧插值；颜色随生命周期插值。render/particles.py 是核心，tests/test_particles.py 15个红。

## 运行

```
python -m pytest tests -q
```

初始状态：15 个用例失败。修复实现使全部用例通过，不要修改 `tests/` 下的测试。

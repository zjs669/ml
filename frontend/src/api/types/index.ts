/**
 * 契约类型总入口。
 *
 * 2026-10 重构把原本 837 行的单文件按域拆开。拆分的目的是「改一个域的类型时
 * 不用在读 800 行里找位置」，而不是改变对外入口 —— 所有既有 `from '@/api/types'`
 * 写法保持不变，改的只是内部组织。
 *
 * 新域类型请新建文件并在此重导出，不要再往单个文件里堆。
 */

export * from './common'
export * from './bazi'
export * from './reverse'
export * from './ziwei'
export * from './liuyao'
export * from './qimen'
export * from './charts'
export * from './reports'
export * from './knowledge'
export * from './billing'
export * from './auth'
export * from './almanac'
export * from './tarot'
export * from './daliuren'
